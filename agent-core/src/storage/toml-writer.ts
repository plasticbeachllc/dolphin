// agent-core/src/storage/toml-writer.ts
import { mkdir, writeFile, rename, unlink, readFile, access } from "fs/promises";
import { dirname } from "path";
import { stringify as tomlStringify, parse as tomlParse } from "@iarna/toml";
import { randomBytes } from "crypto";
import { PathValidator } from "../../../shared/security/path-validator";

export class TOMLWriter<T> {
  private filepath: string;

  constructor(filepath: string, baseDir: string = process.cwd()) {
    // Validate filepath to prevent directory traversal attacks
    const validator = new PathValidator({ baseDir });
    this.filepath = validator.validate(filepath);
  }

  async write(data: T): Promise<void> {
    // Ensure directory exists
    const dir = dirname(this.filepath);
    await mkdir(dir, { recursive: true });

    // Serialize to TOML
    const content = tomlStringify(data as Record<string, unknown>);

    // Create temp file
    const tempFile = `${this.filepath}.tmp-${randomBytes(6).toString("hex")}`;

    try {
      // Write to temp
      await writeFile(tempFile, content, "utf-8");

      // Atomic rename (POSIX)
      await rename(tempFile, this.filepath);
    } catch (error) {
      // Clean up on failure
      await unlink(tempFile).catch(() => {});
      throw error;
    }
  }

  async read(): Promise<T | null> {
    try {
      const content = await readFile(this.filepath, "utf-8");
      return tomlParse(content) as T;
    } catch (error: unknown) {
      if (error instanceof Error && 'code' in error && error.code === "ENOENT") {
        return null; // File doesn't exist yet
      }
      throw error; // Re-throw parse errors or other issues
    }
  }

  async exists(): Promise<boolean> {
    try {
      await access(this.filepath);
      return true;
    } catch {
      return false;
    }
  }

  async delete(): Promise<void> {
    try {
      await unlink(this.filepath);
    } catch (error: unknown) {
      if (!(error instanceof Error && 'code' in error && error.code === "ENOENT")) {
        throw error;
      }
    }
  }
}
