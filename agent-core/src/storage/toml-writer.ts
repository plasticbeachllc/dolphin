// agent-core/src/storage/toml-writer.ts
import * as fs from "fs/promises";
import * as path from "path";
import * as toml from "@iarna/toml";
import { randomBytes } from "crypto";
import { PathValidator } from "../../../../shared/security/path-validator";

export class TOMLWriter<T> {
  private filepath: string;

  constructor(filepath: string, baseDir: string = process.cwd()) {
    // Validate filepath to prevent directory traversal attacks
    const validator = new PathValidator({ baseDir });
    this.filepath = validator.validate(filepath);
  }

  async write(data: T): Promise<void> {
    // Ensure directory exists
    const dir = path.dirname(this.filepath);
    await fs.mkdir(dir, { recursive: true });

    // Serialize to TOML
    const content = toml.stringify(data as any);

    // Create temp file
    const tempFile = `${this.filepath}.tmp-${randomBytes(6).toString("hex")}`;

    try {
      // Write to temp
      await fs.writeFile(tempFile, content, "utf-8");

      // Atomic rename (POSIX)
      await fs.rename(tempFile, this.filepath);
    } catch (error) {
      // Clean up on failure
      await fs.unlink(tempFile).catch(() => {});
      throw error;
    }
  }

  async read(): Promise<T | null> {
    try {
      const content = await fs.readFile(this.filepath, "utf-8");
      return toml.parse(content) as T;
    } catch (error: any) {
      if (error.code === "ENOENT") {
        return null; // File doesn't exist yet
      }
      throw error; // Re-throw parse errors or other issues
    }
  }

  async exists(): Promise<boolean> {
    try {
      await fs.access(this.filepath);
      return true;
    } catch {
      return false;
    }
  }

  async delete(): Promise<void> {
    try {
      await fs.unlink(this.filepath);
    } catch (error: any) {
      if (error.code !== "ENOENT") {
        throw error;
      }
    }
  }
}
