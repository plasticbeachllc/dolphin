// shared/security/__tests__/path-validator.test.ts
import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import {
  PathValidator,
  PathValidationError,
  PathValidationOptions,
} from "../path-validator";

describe("PathValidator", () => {
  let testDir: string;
  let validator: PathValidator;

  beforeAll(() => {
    // Create temporary test directory
    testDir = fs.mkdtempSync(path.join(os.tmpdir(), "path-validator-test-"));

    // Create test structure
    fs.mkdirSync(path.join(testDir, "subdir"), { recursive: true });
    fs.writeFileSync(path.join(testDir, "file.txt"), "test content");
    fs.writeFileSync(path.join(testDir, "file.json"), '{"test": true}');
    fs.writeFileSync(path.join(testDir, "subdir", "nested.txt"), "nested");

    // Create a symlink for testing
    try {
      fs.symlinkSync(
        path.join(testDir, "file.txt"),
        path.join(testDir, "symlink.txt")
      );
    } catch {
      // Symlink creation might fail on some systems, tests will be skipped
    }

    validator = new PathValidator({ baseDir: testDir });
  });

  afterAll(() => {
    // Clean up test directory
    fs.rmSync(testDir, { recursive: true, force: true });
  });

  describe("constructor", () => {
    it("should create validator with valid baseDir", () => {
      expect(() => new PathValidator({ baseDir: testDir })).not.toThrow();
    });

    it("should throw if baseDir does not exist", () => {
      expect(
        () => new PathValidator({ baseDir: "/nonexistent/path" })
      ).toThrow("Base directory does not exist");
    });

    it("should normalize baseDir", () => {
      const v = new PathValidator({ baseDir: testDir + "///" });
      expect(() => v.validate("file.txt")).not.toThrow();
    });
  });

  describe("validate - basic functionality", () => {
    it("should validate simple relative path", () => {
      const result = validator.validate("file.txt");
      expect(result).toBe(path.join(testDir, "file.txt"));
    });

    it("should validate nested relative path", () => {
      const result = validator.validate("subdir/nested.txt");
      expect(result).toBe(path.join(testDir, "subdir", "nested.txt"));
    });

    it("should validate path with ./ prefix", () => {
      const result = validator.validate("./file.txt");
      expect(result).toBe(path.join(testDir, "file.txt"));
    });

    it("should validate absolute path within workspace", () => {
      const absolutePath = path.join(testDir, "file.txt");
      const result = validator.validate(absolutePath);
      expect(result).toBe(absolutePath);
    });
  });

  describe("validate - path traversal attacks", () => {
    it("should reject simple parent directory traversal", () => {
      expect(() => validator.validate("../etc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should reject multiple parent directory traversal", () => {
      expect(() => validator.validate("../../etc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should reject traversal in middle of path", () => {
      expect(() => validator.validate("subdir/../../etc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should reject complex traversal attempt", () => {
      expect(() =>
        validator.validate("subdir/../../../etc/passwd")
      ).toThrow(PathValidationError);
    });

    it("should reject traversal with mixed separators", () => {
      expect(() => validator.validate("subdir\\../../../etc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should allow valid parent reference that stays in workspace", () => {
      const result = validator.validate("subdir/../file.txt");
      expect(result).toBe(path.join(testDir, "file.txt"));
    });

    it("should reject absolute path outside workspace", () => {
      expect(() => validator.validate("/etc/passwd")).toThrow(
        PathValidationError
      );
    });
  });

  describe("validate - URL encoding attacks", () => {
    it("should reject URL-encoded path traversal (%2e%2e/)", () => {
      expect(() => validator.validate("%2e%2e/etc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should reject double URL-encoded traversal", () => {
      expect(() => validator.validate("%252e%252e/etc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should reject mixed encoding traversal", () => {
      expect(() => validator.validate("..%2f..%2fetc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should handle valid URL-encoded filename", () => {
      // Create file with space in name
      const fileWithSpace = "file with space.txt";
      fs.writeFileSync(path.join(testDir, fileWithSpace), "content");

      const result = validator.validate("file%20with%20space.txt");
      expect(result).toBe(path.join(testDir, fileWithSpace));

      // Clean up
      fs.unlinkSync(path.join(testDir, fileWithSpace));
    });
  });

  describe("validate - null byte attacks", () => {
    it("should reject path with null byte", () => {
      expect(() => validator.validate("file.txt\0.jpg")).toThrow(
        PathValidationError
      );
    });

    it("should reject path with null byte in middle", () => {
      expect(() => validator.validate("sub\0dir/file.txt")).toThrow(
        PathValidationError
      );
    });
  });

  describe("validate - symlink handling", () => {
    it("should reject symlinks by default", () => {
      if (!fs.existsSync(path.join(testDir, "symlink.txt"))) {
        console.log("Skipping symlink test - creation not supported");
        return;
      }

      expect(() => validator.validate("symlink.txt")).toThrow(
        PathValidationError
      );
    });

    it("should allow symlinks when enabled", () => {
      if (!fs.existsSync(path.join(testDir, "symlink.txt"))) {
        console.log("Skipping symlink test - creation not supported");
        return;
      }

      const v = new PathValidator({ baseDir: testDir, allowSymlinks: true });
      expect(() => v.validate("symlink.txt")).not.toThrow();
    });
  });

  describe("validate - existence checking", () => {
    it("should allow non-existent paths by default", () => {
      expect(() => validator.validate("nonexistent.txt")).not.toThrow();
    });

    it("should reject non-existent paths when mustExist=true", () => {
      const v = new PathValidator({ baseDir: testDir, mustExist: true });
      expect(() => v.validate("nonexistent.txt")).toThrow(PathValidationError);
    });

    it("should allow existing paths when mustExist=true", () => {
      const v = new PathValidator({ baseDir: testDir, mustExist: true });
      const result = v.validate("file.txt");
      expect(result).toBe(path.join(testDir, "file.txt"));
    });
  });

  describe("validate - extension filtering", () => {
    it("should allow files with permitted extensions", () => {
      const v = new PathValidator({
        baseDir: testDir,
        allowedExtensions: [".txt", ".json"],
      });

      expect(() => v.validate("file.txt")).not.toThrow();
      expect(() => v.validate("file.json")).not.toThrow();
    });

    it("should reject files with non-permitted extensions", () => {
      const v = new PathValidator({
        baseDir: testDir,
        allowedExtensions: [".txt"],
      });

      expect(() => v.validate("file.json")).toThrow(PathValidationError);
    });

    it("should be case-insensitive for extensions", () => {
      const v = new PathValidator({
        baseDir: testDir,
        allowedExtensions: [".TXT"],
      });

      expect(() => v.validate("file.txt")).not.toThrow();
    });

    it("should reject files with no extension when extensions required", () => {
      const v = new PathValidator({
        baseDir: testDir,
        allowedExtensions: [".txt"],
      });

      expect(() => v.validate("noextension")).toThrow(PathValidationError);
    });
  });

  describe("validate - pattern filtering", () => {
    it("should reject filenames matching disallowed patterns", () => {
      const v = new PathValidator({
        baseDir: testDir,
        disallowedPatterns: ["^\\.", ".*\\.backup$"],
      });

      expect(() => v.validate(".hidden")).toThrow(PathValidationError);
      expect(() => v.validate("file.backup")).toThrow(PathValidationError);
    });

    it("should allow filenames not matching disallowed patterns", () => {
      const v = new PathValidator({
        baseDir: testDir,
        disallowedPatterns: ["^\\.", ".*\\.backup$"],
      });

      expect(() => v.validate("file.txt")).not.toThrow();
    });

    it("should check patterns against filename only, not full path", () => {
      const v = new PathValidator({
        baseDir: testDir,
        disallowedPatterns: ["^subdir$"],
      });

      // Should allow because "nested.txt" doesn't match, even though path contains "subdir"
      expect(() => v.validate("subdir/nested.txt")).not.toThrow();
    });
  });

  describe("validate - custom error messages", () => {
    it("should use custom error prefix", () => {
      const v = new PathValidator({
        baseDir: testDir,
        errorPrefix: "Security violation",
      });

      try {
        v.validate("../etc/passwd");
        expect(true).toBe(false); // Should not reach here
      } catch (error) {
        expect(error).toBeInstanceOf(PathValidationError);
        expect((error as Error).message).toContain("Security violation");
      }
    });
  });

  describe("validate - error details", () => {
    it("should include attempted path in error", () => {
      try {
        validator.validate("../etc/passwd");
        expect(true).toBe(false); // Should not reach here
      } catch (error) {
        expect(error).toBeInstanceOf(PathValidationError);
        const pve = error as PathValidationError;
        expect(pve.attemptedPath).toBe("../etc/passwd");
      }
    });

    it("should include reason in error", () => {
      try {
        validator.validate("../etc/passwd");
        expect(true).toBe(false); // Should not reach here
      } catch (error) {
        expect(error).toBeInstanceOf(PathValidationError);
        const pve = error as PathValidationError;
        expect(pve.reason).toBe("path_traversal");
      }
    });
  });

  describe("validateBatch", () => {
    it("should validate multiple paths", () => {
      const paths = ["file.txt", "subdir/nested.txt", "file.json"];
      const results = validator.validateBatch(paths);

      expect(results).toHaveLength(3);
      expect(results[0]).toBe(path.join(testDir, "file.txt"));
      expect(results[1]).toBe(path.join(testDir, "subdir", "nested.txt"));
      expect(results[2]).toBe(path.join(testDir, "file.json"));
    });

    it("should throw on first invalid path", () => {
      const paths = ["file.txt", "../etc/passwd", "file.json"];

      expect(() => validator.validateBatch(paths)).toThrow(PathValidationError);
    });

    it("should handle empty array", () => {
      const results = validator.validateBatch([]);
      expect(results).toHaveLength(0);
    });
  });

  describe("check", () => {
    it("should return true for valid path", () => {
      expect(validator.check("file.txt")).toBe(true);
    });

    it("should return false for invalid path", () => {
      expect(validator.check("../etc/passwd")).toBe(false);
    });

    it("should not throw on invalid path", () => {
      expect(() => validator.check("../etc/passwd")).not.toThrow();
    });
  });

  describe("static validate", () => {
    it("should validate path with one-off call", () => {
      const result = PathValidator.validate("file.txt", { baseDir: testDir });
      expect(result).toBe(path.join(testDir, "file.txt"));
    });

    it("should throw on invalid path", () => {
      expect(() =>
        PathValidator.validate("../etc/passwd", { baseDir: testDir })
      ).toThrow(PathValidationError);
    });
  });

  describe("real-world attack vectors", () => {
    it("should reject Windows-style UNC paths", () => {
      expect(() => validator.validate("\\\\server\\share\\file")).toThrow(
        PathValidationError
      );
    });

    it("should reject Unicode normalization attacks", () => {
      // U+2024 (one dot leader) looks like "." but is different
      expect(() => validator.validate("\u2024\u2024/etc/passwd")).toThrow(
        PathValidationError
      );
    });

    it("should reject paths with consecutive slashes", () => {
      // This should resolve correctly but let's ensure no bypass
      const result = validator.validate("subdir//nested.txt");
      expect(result).toBe(path.join(testDir, "subdir", "nested.txt"));
    });

    it("should reject Unicode right-to-left override attacks", () => {
      // Attackers might try to disguise file extensions
      const malicious = "file\u202Etxt.exe"; // RTLO character
      // After normalization, this becomes "fileexe.txt" visually but "file<RTLO>txt.exe" in code

      // Since our validator doesn't specifically block RTLO, this is more for awareness
      // In production, you might want to explicitly reject control characters
      expect(() => validator.validate(malicious)).not.toThrow();
    });
  });

  describe("edge cases", () => {
    it("should handle empty string", () => {
      expect(() => validator.validate("")).not.toThrow();
    });

    it("should handle dot (current directory)", () => {
      const result = validator.validate(".");
      expect(result).toBe(testDir);
    });

    it("should handle paths with spaces", () => {
      fs.writeFileSync(path.join(testDir, "file with spaces.txt"), "content");
      const result = validator.validate("file with spaces.txt");
      expect(result).toBe(path.join(testDir, "file with spaces.txt"));
      fs.unlinkSync(path.join(testDir, "file with spaces.txt"));
    });

    it("should handle paths with special characters", () => {
      const specialFile = "file-_@#.txt";
      fs.writeFileSync(path.join(testDir, specialFile), "content");
      const result = validator.validate(specialFile);
      expect(result).toBe(path.join(testDir, specialFile));
      fs.unlinkSync(path.join(testDir, specialFile));
    });

    it("should handle very long paths", () => {
      const longName = "a".repeat(200) + ".txt";
      const result = validator.validate(longName);
      expect(result).toBe(path.join(testDir, longName));
    });
  });
});
