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
  const originalProvider = process.env.DOLPHIN_LLM_PROVIDER;
  const originalModel = process.env.DOLPHIN_LLM_MODEL;
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
    if (originalProvider) {
      process.env.DOLPHIN_LLM_PROVIDER = originalProvider;
    } else {
      delete process.env.DOLPHIN_LLM_PROVIDER;
    }
    if (originalModel) {
      process.env.DOLPHIN_LLM_MODEL = originalModel;
    } else {
      delete process.env.DOLPHIN_LLM_MODEL;
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

  it("accepts provider selection via DOLPHIN_LLM_PROVIDER", () => {
    process.env.DOLPHIN_LLM_PROVIDER = "openai";
    process.env.DOLPHIN_LLM_MODEL = "gpt-5.1";
    const settings = loadProviderSettings();
    expect(settings.provider).toBe("openai");
    expect(settings.model).toBe("gpt-5.1");
  });

  it("falls back to legacy env vars when LLM-specific ones are missing", () => {
    process.env.DOLPHIN_PROVIDER = "anthropic";
    process.env.DOLPHIN_MODEL = "claude-sonnet";
    const settings = loadProviderSettings();
    expect(settings.provider).toBe("anthropic");
    expect(settings.model).toBe("claude-sonnet");
  });
});
