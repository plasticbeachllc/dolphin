import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { parse as parseToml } from "@iarna/toml";

export interface ProviderSettings {
  provider?: "anthropic" | "openai";
  model?: string;
  temperature?: number;
  openAIBaseUrl?: string;
  openAIApiKey?: string;
}

export function loadProviderSettings(): ProviderSettings {
  const fromEnv: ProviderSettings = {};
  const providerEnv = process.env.DOLPHIN_LLM_PROVIDER ?? process.env.DOLPHIN_PROVIDER;
  if (providerEnv) {
    const provider = providerEnv.toLowerCase();
    if (provider === "anthropic" || provider === "openai") {
      fromEnv.provider = provider;
    }
  }
  const modelEnv = process.env.DOLPHIN_LLM_MODEL ?? process.env.DOLPHIN_MODEL;
  if (modelEnv) {
    fromEnv.model = modelEnv;
  }
  if (process.env.DOLPHIN_TEMPERATURE) {
    const parsed = Number(process.env.DOLPHIN_TEMPERATURE);
    if (!Number.isNaN(parsed)) {
      fromEnv.temperature = parsed;
    }
  }
  if (process.env.DOLPHIN_OPENAI_BASE_URL) {
    fromEnv.openAIBaseUrl = process.env.DOLPHIN_OPENAI_BASE_URL;
  } else if (process.env.OPENAI_BASE_URL) {
    fromEnv.openAIBaseUrl = process.env.OPENAI_BASE_URL;
  }
  if (process.env.DOLPHIN_OPENAI_API_KEY) {
    fromEnv.openAIApiKey = process.env.DOLPHIN_OPENAI_API_KEY;
  }

  const configPath = getConfigPath();
  if (!configPath || !existsSync(configPath)) {
    return fromEnv;
  }

  try {
    const raw = readFileSync(configPath, "utf-8");
    if (!raw.trim()) {
      return fromEnv;
    }
    const parsed = parseToml(raw) as Record<string, unknown>;
    const providerSection = parsed.provider as Record<string, unknown> | undefined;
    const resolved: ProviderSettings = { ...fromEnv };

    if (providerSection) {
      if (typeof providerSection.provider === "string") {
        const provider = providerSection.provider.toLowerCase();
        if (provider === "anthropic" || provider === "openai") {
          resolved.provider = provider;
        }
      }
      if (typeof providerSection.model === "string") {
        resolved.model = providerSection.model;
      }
      if (typeof providerSection.temperature === "number") {
        resolved.temperature = providerSection.temperature;
      }
      const openAISection = providerSection.openai as Record<string, unknown> | undefined;
      if (openAISection) {
        if (typeof openAISection.base_url === "string") {
          resolved.openAIBaseUrl = openAISection.base_url;
        }
        if (typeof openAISection.api_key === "string") {
          resolved.openAIApiKey = openAISection.api_key;
        }
      }
    }

    return resolved;
  } catch (error) {
    console.warn(`[ProviderSettings] Failed to parse config: ${error}`);
    return fromEnv;
  }
}

function getConfigPath(): string | null {
  if (process.env.DOLPHIN_CONFIG_PATH) {
    return process.env.DOLPHIN_CONFIG_PATH;
  }
  const dir = join(homedir(), ".dolphin");
  const tomlPath = join(dir, "config.toml");
  if (existsSync(tomlPath)) {
    return tomlPath;
  }
  const legacyPath = join(dir, "config");
  if (existsSync(legacyPath)) {
    return legacyPath;
  }
  return null;
}
