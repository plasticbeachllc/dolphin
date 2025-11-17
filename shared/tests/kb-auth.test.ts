import { describe, it, expect, beforeEach } from "bun:test";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { getKbKeyPath, getOrCreateKbApiKey, resolveKbApiKey } from "../kb-auth";

function makeTempHome(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "kb-auth-"));
}

describe("kb-auth", () => {
  beforeEach(() => {
    delete process.env.DOLPHIN_API_KEY;
    delete process.env.DOLPHIN_KB_API_KEY;
  });

  it("prefers environment override", () => {
    process.env.DOLPHIN_API_KEY = "env-key";

    const resolved = resolveKbApiKey();
    const created = getOrCreateKbApiKey();

    expect(resolved).toBe("env-key");
    expect(created).toBe("env-key");
  });

  it("creates key file when missing", () => {
    const homeDir = makeTempHome();

    const key = getOrCreateKbApiKey({ homeDir });

    const keyPath = getKbKeyPath({ homeDir });
    expect(fs.existsSync(keyPath)).toBeTrue();
    expect(fs.readFileSync(keyPath, "utf8").trim()).toBe(key);
    expect(key).toHaveLength(64);
  });

  it("reuses existing key on subsequent calls", () => {
    const homeDir = makeTempHome();

    const first = getOrCreateKbApiKey({ homeDir });
    const second = getOrCreateKbApiKey({ homeDir });

    expect(first).toBe(second);
  });

  it("resolve returns undefined when file missing", () => {
    const homeDir = makeTempHome();

    const result = resolveKbApiKey({ homeDir });
    expect(result).toBeUndefined();
  });

  it("resolve reads key file without creating", () => {
    const homeDir = makeTempHome();
    const keyPath = getKbKeyPath({ homeDir });
    fs.mkdirSync(path.dirname(keyPath), { recursive: true });
    fs.writeFileSync(keyPath, "file-key\n", { encoding: "utf8" });

    const resolved = resolveKbApiKey({ homeDir });
    expect(resolved).toBe("file-key");
  });
});
