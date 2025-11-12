// shared/security/path-validator.ts
import * as path from "path";
import * as fs from "fs";

/**
 * Options for path validation
 */
export interface PathValidationOptions {
  /** Base directory - paths must resolve within this directory */
  baseDir: string;
  /** Allow symlinks (default: false for security) */
  allowSymlinks?: boolean;
  /** Require path to exist (default: false) */
  mustExist?: boolean;
  /** Allowed file extensions (e.g., [".txt", ".json"]) */
  allowedExtensions?: string[];
  /** Disallowed filename patterns (regex strings) */
  disallowedPatterns?: string[];
  /** Custom error message prefix */
  errorPrefix?: string;
}

/**
 * Custom error class for path validation failures
 */
export class PathValidationError extends Error {
  constructor(
    message: string,
    public readonly attemptedPath: string,
    public readonly reason: string
  ) {
    super(message);
    this.name = "PathValidationError";
    Object.setPrototypeOf(this, PathValidationError.prototype);
  }
}

/**
 * Secure path validator to prevent directory traversal attacks
 *
 * Key security features:
 * - Rejects absolute paths outside baseDir
 * - Detects path traversal attempts (../)
 * - Optionally validates symlinks
 * - Extension and pattern filtering
 * - URL-encoding attack prevention
 *
 * @example
 * ```typescript
 * const validator = new PathValidator({ baseDir: "/workspace" });
 * const safePath = validator.validate("data/file.txt"); // OK
 * validator.validate("../etc/passwd"); // Throws PathValidationError
 * ```
 */
export class PathValidator {
  private readonly baseDir: string;
  private readonly options: Required<
    Omit<PathValidationOptions, "allowedExtensions" | "disallowedPatterns" | "errorPrefix">
  > & {
    allowedExtensions?: string[];
    disallowedPatterns?: string[];
    errorPrefix?: string;
  };

  constructor(options: PathValidationOptions) {
    // Normalize and resolve base directory
    this.baseDir = path.resolve(path.normalize(options.baseDir));
    this.options = {
      baseDir: this.baseDir,
      allowSymlinks: options.allowSymlinks ?? false,
      mustExist: options.mustExist ?? false,
      allowedExtensions: options.allowedExtensions,
      disallowedPatterns: options.disallowedPatterns,
      errorPrefix: options.errorPrefix,
    };

    // Validate base directory exists
    if (!fs.existsSync(this.baseDir)) {
      throw new Error(`Base directory does not exist: ${this.baseDir}`);
    }
  }

  /**
   * Validate a single path and return the absolute resolved path
   *
   * @param inputPath - Path to validate (relative or absolute)
   * @returns Absolute path within baseDir
   * @throws PathValidationError if validation fails
   */
  validate(inputPath: string): string {
    const prefix = this.options.errorPrefix || "Access denied";

    // Decode URL-encoded paths to prevent bypass attempts
    let decodedPath = inputPath;
    try {
      decodedPath = decodeURIComponent(inputPath);
    } catch {
      // If decode fails, use original (might be already decoded)
      decodedPath = inputPath;
    }

    // Reject paths with null bytes (directory traversal technique)
    if (decodedPath.includes("\0")) {
      throw new PathValidationError(
        `${prefix}: null byte in path`,
        inputPath,
        "null_byte"
      );
    }

    // Reject absolute paths that don't start with baseDir
    if (path.isAbsolute(decodedPath)) {
      const normalized = path.normalize(decodedPath);
      if (!normalized.startsWith(this.baseDir)) {
        throw new PathValidationError(
          `${prefix}: absolute paths outside workspace not allowed`,
          inputPath,
          "absolute_path_outside_workspace"
        );
      }
    }

    // Resolve path relative to baseDir
    const resolvedPath = path.resolve(this.baseDir, decodedPath);
    const normalizedPath = path.normalize(resolvedPath);

    // Critical: Check if resolved path escapes baseDir
    const relativePath = path.relative(this.baseDir, normalizedPath);
    const escapesWorkspace =
      relativePath.startsWith("..") || path.isAbsolute(relativePath);

    if (escapesWorkspace) {
      throw new PathValidationError(
        `${prefix}: path resolves outside workspace (attempted: ${inputPath})`,
        inputPath,
        "path_traversal"
      );
    }

    // Check if path exists (if required)
    if (this.options.mustExist && !fs.existsSync(normalizedPath)) {
      throw new PathValidationError(
        `${prefix}: path does not exist`,
        inputPath,
        "not_found"
      );
    }

    // Check for symlinks (if not allowed)
    if (!this.options.allowSymlinks && fs.existsSync(normalizedPath)) {
      try {
        const stats = fs.lstatSync(normalizedPath);
        if (stats.isSymbolicLink()) {
          throw new PathValidationError(
            `${prefix}: symlinks not allowed`,
            inputPath,
            "symlink"
          );
        }
      } catch (error) {
        if (error instanceof PathValidationError) {
          throw error;
        }
        // If lstat fails, path might not exist yet (which is OK if mustExist=false)
      }
    }

    // Check file extension (if specified)
    if (this.options.allowedExtensions) {
      const ext = path.extname(normalizedPath).toLowerCase();
      const allowed = this.options.allowedExtensions.map((e) =>
        e.toLowerCase()
      );
      if (!allowed.includes(ext)) {
        throw new PathValidationError(
          `${prefix}: file extension '${ext}' not allowed`,
          inputPath,
          "invalid_extension"
        );
      }
    }

    // Check disallowed patterns (if specified)
    if (this.options.disallowedPatterns) {
      const filename = path.basename(normalizedPath);
      for (const pattern of this.options.disallowedPatterns) {
        const regex = new RegExp(pattern);
        if (regex.test(filename)) {
          throw new PathValidationError(
            `${prefix}: filename matches disallowed pattern`,
            inputPath,
            "disallowed_pattern"
          );
        }
      }
    }

    return normalizedPath;
  }

  /**
   * Validate multiple paths in batch
   *
   * @param paths - Array of paths to validate
   * @returns Array of absolute paths
   * @throws PathValidationError if any validation fails
   */
  validateBatch(paths: string[]): string[] {
    return paths.map((p) => this.validate(p));
  }

  /**
   * Check if a path would be valid without throwing
   *
   * @param inputPath - Path to check
   * @returns true if valid, false otherwise
   */
  check(inputPath: string): boolean {
    try {
      this.validate(inputPath);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Static convenience method for one-off validation
   */
  static validate(inputPath: string, options: PathValidationOptions): string {
    const validator = new PathValidator(options);
    return validator.validate(inputPath);
  }
}
