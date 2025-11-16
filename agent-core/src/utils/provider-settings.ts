import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { parse as parseToml } from "@iarna/toml";

export interface ProviderSettings {
  provider?: "anthropic" | "openai";
  model?: string;
  temperature?: number;
}

export function loadProviderSettings(): ProviderSettings {
  const fromEnv: ProviderSettings = {};
  if (process.env.DOLPHIN_PROVIDER) {
    const provider = process.env.DOLPHIN_PROVIDER.toLowerCase();
    if (provider === "anthropic" || provider === "openai") {
      fromEnv.provider = provider;
    }
  }
  if (process.env.DOLPHIN_MODEL) {
    fromEnv.model = process.env.DOLPHIN_MODEL;
  }
  if (process.env.DOLPHIN_TEMPERATURE) {
    const parsed = Number(process.env.DOLPHIN_TEMPERATURE);
    if (!Number.isNaN(parsed)) {
      fromEnv.temperature = parsed;
    }
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
    }

    return resolved;
  } catch (error) {
    console.warn(`[ProviderSettings] Failed to parse config: ${error}`);
    return fromEnv;
  }
}

function getConfigPath(): string | null {
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
