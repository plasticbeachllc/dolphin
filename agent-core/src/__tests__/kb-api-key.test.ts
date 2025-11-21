/* eslint-disable @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access */
import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { initializeKbApiKeyEnvGlobal } from "../main";
import { getKbKeyPath, resolveKbApiKey } from "../../../shared/kb-auth";

describe("Agent Core KB API key env init", () => {
  let testHomeDir: string;
  let originalEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    testHomeDir = fs.mkdtempSync(path.join(os.tmpdir(), "agent-kb-test-"));
    originalEnv = { ...process.env };
    delete process.env.DOLPHIN_API_KEY;
    delete process.env.DOLPHIN_KB_API_KEY;
  });

  afterEach(() => {
    process.env = originalEnv;
    if (fs.existsSync(testHomeDir)) {
      fs.rmSync(testHomeDir, { recursive: true, force: true });
    }
  });

  it("keeps existing env key and avoids filesystem access", () => {
    const envCopy: NodeJS.ProcessEnv = { ...process.env, DOLPHIN_API_KEY: "pre-set-env" };
    const key = initializeKbApiKeyEnvGlobal({ env: envCopy, homeDir: testHomeDir });

    expect(key).toBe("pre-set-env");
    const keyPath = getKbKeyPath({ homeDir: testHomeDir });
    expect(fs.existsSync(keyPath)).toBe(false);
    expect(envCopy.DOLPHIN_KB_API_KEY).toBeUndefined();
  });

  it("populates env from managed key file when env is empty", () => {
    fs.mkdirSync(path.join(testHomeDir, ".dolphin"), { recursive: true });
    const keyPath = getKbKeyPath({ homeDir: testHomeDir });
    const fileKey = "file-key-from-managed-store";
    fs.writeFileSync(keyPath, fileKey + "\n", { encoding: "utf8" });
    expect(fs.existsSync(keyPath)).toBe(true);
    const resolvedDirect = resolveKbApiKey({ readOnly: true, homeDir: testHomeDir });
    expect(resolvedDirect).toBe(fileKey);
    const envCopy: NodeJS.ProcessEnv = { ...process.env };

    const resolved = initializeKbApiKeyEnvGlobal({ env: envCopy, homeDir: testHomeDir });

    expect(resolved).toBe(fileKey);
    expect(envCopy.DOLPHIN_API_KEY).toBe(fileKey);
    expect(envCopy.DOLPHIN_KB_API_KEY).toBe(fileKey);
  });

  it("leaves env unset when neither env nor file exists", () => {
    const envCopy: NodeJS.ProcessEnv = { ...process.env };

    const resolved = initializeKbApiKeyEnvGlobal({ env: envCopy, homeDir: testHomeDir });

    expect(resolved).toBeUndefined();
    expect(envCopy.DOLPHIN_API_KEY).toBeUndefined();
    expect(envCopy.DOLPHIN_KB_API_KEY).toBeUndefined();
  });
});
