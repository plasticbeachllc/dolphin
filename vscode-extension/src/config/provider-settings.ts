import {
  DEFAULT_MODEL_BY_PROVIDER,
  MODEL_IDS_BY_PROVIDER,
  type ProviderId,
} from "./provider-options";

export type SupportedProvider = ProviderId;

export const DEFAULT_MODELS: Record<SupportedProvider, string> = DEFAULT_MODEL_BY_PROVIDER;

export const SUPPORTED_MODELS: Record<SupportedProvider, string[]> = MODEL_IDS_BY_PROVIDER;

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

export function resolveProviderSettings(input: ProviderSettingsInput): ProviderSettingsResult {
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
