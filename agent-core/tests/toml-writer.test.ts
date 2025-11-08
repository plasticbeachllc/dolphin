// agent-core/tests/toml-writer.test.ts
import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { TOMLWriter } from "../src/storage/toml-writer";
import * as fs from "fs/promises";
import * as path from "path";
import * as os from "os";

describe("TOMLWriter", () => {
  let testDir: string;
  let testFile: string;

  beforeEach(async () => {
    testDir = path.join(os.tmpdir(), `dolphin-toml-test-${Date.now()}`);
    await fs.mkdir(testDir, { recursive: true });
    testFile = path.join(testDir, "test.toml");
  });

  afterEach(async () => {
    await fs.rm(testDir, { recursive: true, force: true });
  });

  test("writes and reads simple data", async () => {
    const writer = new TOMLWriter<{ name: string; value: number }>(testFile);
    const data = { name: "test", value: 42 };

    await writer.write(data);

    const result = await writer.read();
    expect(result).toEqual(data);
  });

  test("returns null for non-existent file", async () => {
    const writer = new TOMLWriter<any>(testFile);
    const result = await writer.read();
    expect(result).toBeNull();
  });

  test("overwrites existing file", async () => {
    const writer = new TOMLWriter<{ value: number }>(testFile);

    await writer.write({ value: 1 });
    await writer.write({ value: 2 });

    const result = await writer.read();
    expect(result).toEqual({ value: 2 });
  });

  test("creates parent directories", async () => {
    const nestedFile = path.join(testDir, "nested", "deep", "test.toml");
    const writer = new TOMLWriter<{ test: boolean }>(nestedFile);

    await writer.write({ test: true });

    const result = await writer.read();
    expect(result).toEqual({ test: true });

    // Verify directory was created
    const dirExists = await fs
      .access(path.dirname(nestedFile))
      .then(() => true)
      .catch(() => false);
    expect(dirExists).toBe(true);
  });

  test("exists() returns correct status", async () => {
    const writer = new TOMLWriter<any>(testFile);

    expect(await writer.exists()).toBe(false);

    await writer.write({ test: true });

    expect(await writer.exists()).toBe(true);
  });

  test("delete() removes file", async () => {
    const writer = new TOMLWriter<any>(testFile);

    await writer.write({ test: true });
    expect(await writer.exists()).toBe(true);

    await writer.delete();
    expect(await writer.exists()).toBe(false);
  });

  test("delete() handles non-existent file gracefully", async () => {
    const writer = new TOMLWriter<any>(testFile);

    // Should not throw
    await expect(writer.delete()).resolves.toBeUndefined();
  });

  test("atomic write prevents corruption", async () => {
    const writer = new TOMLWriter<{ value: number }>(testFile);

    // Write initial data
    await writer.write({ value: 1 });

    // Rapid concurrent writes
    await Promise.all([
      writer.write({ value: 2 }),
      writer.write({ value: 3 }),
      writer.write({ value: 4 }),
    ]);

    // Should have valid data (one of the values)
    const result = await writer.read();
    expect(result).toBeTruthy();
    expect(result?.value).toBeGreaterThanOrEqual(2);
    expect(result?.value).toBeLessThanOrEqual(4);
  });

  test("handles complex nested data", async () => {
    interface ComplexData {
      plan: {
        id: string;
        status: string;
      };
      steps: Array<{
        id: string;
        order: number;
        description: string;
      }>;
    }

    const writer = new TOMLWriter<ComplexData>(testFile);
    const data: ComplexData = {
      plan: {
        id: "test-plan-1",
        status: "pending",
      },
      steps: [
        { id: "step-1", order: 1, description: "First step" },
        { id: "step-2", order: 2, description: "Second step" },
      ],
    };

    await writer.write(data);
    const result = await writer.read();

    expect(result).toEqual(data);
    expect(result?.steps).toHaveLength(2);
    expect(result?.steps[0].description).toBe("First step");
  });

  test("preserves TOML formatting", async () => {
    const writer = new TOMLWriter<{ title: string; value: number }>(testFile);
    await writer.write({ title: "Test Document", value: 123 });

    const content = await fs.readFile(testFile, "utf-8");

    // Verify TOML format
    expect(content).toContain('title = "Test Document"');
    expect(content).toContain("value = 123");
  });
});