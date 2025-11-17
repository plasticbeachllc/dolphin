export type SupportedProvider = "anthropic" | "openai";

export const DEFAULT_MODELS: Record<SupportedProvider, string> = {
  anthropic: "claude-sonnet-4-5-20250929",
  openai: "gpt-5.1-codex",
};

export const SUPPORTED_MODELS: Record<SupportedProvider, string[]> = {
  anthropic: [
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
  ],
  openai: ["gpt-5.1", "gpt-5.1-codex", "gpt-5.1-codex-mini"],
};

export interface ProviderSettingsInput {
  provider?: string | null;
  anthropicModel?: string | null;
  openaiModel?: string | null;
}

export interface ProviderSettingsResult {
  provider: SupportedProvider;
  model: string;
  warnings: string[];
}

export function resolveProviderSettings(
  input: ProviderSettingsInput
): ProviderSettingsResult {
  const normalizedProvider = (input.provider ?? "anthropic").toLowerCase();
  let provider: SupportedProvider = normalizedProvider === "openai" ? "openai" : "anthropic";
  const warnings: string[] = [];

  if (normalizedProvider && normalizedProvider !== "anthropic" && normalizedProvider !== "openai") {
    warnings.push(`Unknown provider "${normalizedProvider}". Falling back to Anthropic.`);
  }

  const modelCandidate = provider === "anthropic" ? input.anthropicModel : input.openaiModel;
  const model = normalizeModel(provider, modelCandidate, warnings);

  return { provider, model, warnings };
}

function normalizeModel(
  provider: SupportedProvider,
  candidate: string | null | undefined,
  warnings: string[]
): string {
  if (candidate && SUPPORTED_MODELS[provider].includes(candidate)) {
    return candidate;
  }

  if (candidate && !SUPPORTED_MODELS[provider].includes(candidate)) {
    warnings.push(
      `Model "${candidate}" is not supported for ${provider}. Falling back to ${DEFAULT_MODELS[provider]}.`
    );
  }

  return DEFAULT_MODELS[provider];
}
