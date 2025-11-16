import { describe, it, expect, afterEach } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";

import { loadProviderSettings } from "../../../src/utils/provider-settings";

describe("loadProviderSettings", () => {
  const originalHome = process.env.HOME;
  const originalConfigPath = process.env.DOLPHIN_CONFIG_PATH;
  const originalBase = process.env.DOLPHIN_OPENAI_BASE_URL;
  const originalKey = process.env.DOLPHIN_OPENAI_API_KEY;
  const createdDirs: string[] = [];

  afterEach(() => {
    if (originalHome) {
      process.env.HOME = originalHome;
    } else {
      delete process.env.HOME;
    }
    if (originalBase) {
      process.env.DOLPHIN_OPENAI_BASE_URL = originalBase;
    } else {
      delete process.env.DOLPHIN_OPENAI_BASE_URL;
    }
    if (originalConfigPath) {
      process.env.DOLPHIN_CONFIG_PATH = originalConfigPath;
    } else {
      delete process.env.DOLPHIN_CONFIG_PATH;
    }
    if (originalKey) {
      process.env.DOLPHIN_OPENAI_API_KEY = originalKey;
    } else {
      delete process.env.DOLPHIN_OPENAI_API_KEY;
    }
    for (const dir of createdDirs.splice(0)) {
      try {
        rmSync(dir, { recursive: true, force: true });
      } catch {
        // ignore cleanup errors in CI
      }
    }
  });

  it("pulls OpenAI-compatible overrides from the config file", () => {
    const home = mkdtempSync(join(tmpdir(), "dolphin-provider-"));
    createdDirs.push(home);
    const configDir = join(home, ".dolphin");
    mkdirSync(configDir, { recursive: true });
    const configPath = join(configDir, "config.toml");
    const configBody = [
      "[provider]",
      'provider = "openai"',
      "",
      "[provider.openai]",
      'base_url = "https://lab"',
      'api_key = "sk-config"',
      "",
    ].join("\n");
    writeFileSync(configPath, configBody);
    process.env.DOLPHIN_CONFIG_PATH = configPath;

    const settings = loadProviderSettings();
    expect(settings.provider).toBe("openai");
    expect(settings.openAIBaseUrl).toBe("https://lab");
    expect(settings.openAIApiKey).toBe("sk-config");
  });

  it("prefers env overrides for base URL", () => {
    process.env.DOLPHIN_OPENAI_BASE_URL = "https://env";
    const settings = loadProviderSettings();
    expect(settings.openAIBaseUrl).toBe("https://env");
  });
});
