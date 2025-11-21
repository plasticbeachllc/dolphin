import type { ProviderAuthStatus } from "../types/auth";

export type ProviderId = "anthropic" | "openai";

export interface ProviderOption {
  id: ProviderId;
  label: string;
  description: string;
  availabilitySetting: `dolphin.llm.model.${ProviderId}` | "dolphin.llm.provider";
  setSecretCommand: string;
  secretSetting: string;
  secretDescription: string;
}

export interface ProviderModelOption {
  id: string;
  provider: ProviderId;
  label: string;
  description: string;
  default?: boolean;
}

export const PROVIDER_OPTIONS: ProviderOption[] = [
  {
    id: "anthropic",
    label: "Anthropic (Claude 4.5)",
    description: "Use Claude Sonnet/Haiku for Dolphin workflows.",
    availabilitySetting: "dolphin.llm.provider",
    setSecretCommand: "dolphin.setClaudeApiKey",
    secretSetting: "dolphin.anthropicApiKey",
    secretDescription: "Anthropic API key stored via VS Code SecretStorage.",
  },
  {
    id: "openai",
    label: "OpenAI (GPT-5.1 family)",
    description: "Use GPT-5.1 models for Dolphin workflows.",
    availabilitySetting: "dolphin.llm.provider",
    setSecretCommand: "dolphin.setOpenAIApiKey",
    secretSetting: "dolphin.openaiApiKey",
    secretDescription: "OpenAI API key stored via VS Code SecretStorage.",
  },
];

const PROVIDER_MODEL_OPTIONS: ProviderModelOption[] = [
  {
    id: "claude-sonnet-4-5-20250929",
    provider: "anthropic",
    label: "Claude Sonnet 4.5 (September 2025)",
    description: "Latest Sonnet 4.5 drop with stability fixes.",
    default: true,
  },
  {
    id: "claude-sonnet-4-5",
    provider: "anthropic",
    label: "Claude Sonnet 4.5",
    description: "General-purpose Claude model optimized for code generation.",
  },
  {
    id: "claude-haiku-4-5",
    provider: "anthropic",
    label: "Claude Haiku 4.5",
    description: "Lightweight Claude model for quick iterations.",
  },
  {
    id: "gpt-5.1",
    provider: "openai",
    label: "GPT-5.1",
    description: "General-purpose GPT model for architect workflows.",
  },
  {
    id: "gpt-5.1-codex",
    provider: "openai",
    label: "GPT-5.1 Codex",
    description: "OpenAI code-focused GPT model.",
    default: true,
  },
  {
    id: "gpt-5.1-codex-mini",
    provider: "openai",
    label: "GPT-5.1 Codex Mini",
    description: "Lower-latency GPT Codex variant.",
  },
];

export const PROVIDER_IDS = PROVIDER_OPTIONS.map((option) => option.id);

export const PROVIDER_LABELS: Record<ProviderId, string> = Object.fromEntries(
  PROVIDER_OPTIONS.map((option) => [option.id, option.label])
) as Record<ProviderId, string>;

export const PROVIDER_SECRET_COMMANDS: Record<ProviderId, string> = Object.fromEntries(
  PROVIDER_OPTIONS.map((option) => [option.id, option.setSecretCommand])
) as Record<ProviderId, string>;

export const DEFAULT_MODEL_BY_PROVIDER: Record<ProviderId, string> = Object.fromEntries(
  PROVIDER_MODEL_OPTIONS.filter((model) => model.default).map((model) => [model.provider, model.id])
) as Record<ProviderId, string>;

export const MODELS_BY_PROVIDER: Record<ProviderId, ProviderModelOption[]> = {
  anthropic: PROVIDER_MODEL_OPTIONS.filter((model) => model.provider === "anthropic"),
  openai: PROVIDER_MODEL_OPTIONS.filter((model) => model.provider === "openai"),
};

export const MODEL_IDS_BY_PROVIDER: Record<ProviderId, string[]> = {
  anthropic: MODELS_BY_PROVIDER.anthropic.map((model) => model.id),
  openai: MODELS_BY_PROVIDER.openai.map((model) => model.id),
};

export function getProviderOption(provider: ProviderId): ProviderOption {
  const option = PROVIDER_OPTIONS.find((entry) => entry.id === provider);
  if (!option) {
    throw new Error(`Unknown provider: ${provider}`);
  }
  return option;
}

export function getProviderModels(provider: ProviderId): ProviderModelOption[] {
  return MODELS_BY_PROVIDER[provider];
}

export function findModel(provider: ProviderId, modelId: string): ProviderModelOption | undefined {
  return MODELS_BY_PROVIDER[provider].find((model) => model.id === modelId);
}

export function summarizeAuthStatus(status: ProviderAuthStatus): string {
  if (!status.authenticated) {
    return `${status.provider} missing credentials`;
  }
  return `${status.provider} authenticated via ${status.mode}`;
}
