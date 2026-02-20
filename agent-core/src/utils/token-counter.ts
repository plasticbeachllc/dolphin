import Anthropic from "@anthropic-ai/sdk";
import { encoding_for_model, get_encoding, type Tiktoken } from "tiktoken";
import { createHash } from "node:crypto";

export type TokenCountMode = "exact" | "estimate";

export interface TokenCountResult {
  mode: TokenCountMode;
  model: string;
  totalTokens: number;
  perInput: number[];
  cacheHits: number;
  cacheMisses: number;
  usedCache: boolean;
  timestamp: number;
  estimationError?: number;
}

export interface TokenCountOptions {
  model?: string;
  provider?: string;
  baseUrl?: string;
}

export interface TokenCounterMetrics {
  cacheSize: number;
  cacheHits: number;
  cacheMisses: number;
  anthropicCalls: number;
  anthropicErrors: number;
  openaiCounts: number;
  openaiErrors: number;
  estimationCharsPerToken: number;
  averageEstimationError: number;
  calibrationSamples: number;
  estimationSamples: number;
  lastMode: TokenCountMode;
}

export interface TokenCounterConfig {
  defaultModel: string;
  cacheTTLms: number;
  cacheMaxEntries: number;
  estimationCharsPerToken: number;
  calibrationWindow: number;
}

interface CacheEntry {
  tokens: number;
  expiresAt: number;
  lastAccessed: number;
}

type CountTokensResponse = {
  input_tokens: number;
};

function isCountTokensResponse(value: unknown): value is CountTokensResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "input_tokens" in value &&
    typeof (value as { input_tokens: unknown }).input_tokens === "number"
  );
}

export interface TokenCounterLike {
  countExact(texts: string[], options?: TokenCountOptions): Promise<TokenCountResult>;
  estimate(texts: string[], options?: TokenCountOptions): TokenCountResult;
  collectMetrics(): TokenCounterMetrics;
}

const DEFAULT_CONFIG: TokenCounterConfig = {
  defaultModel: "claude-sonnet-4-5-20250929",
  cacheTTLms: 15 * 60 * 1000,
  cacheMaxEntries: 512,
  estimationCharsPerToken: 4,
  calibrationWindow: 100,
};

export class AnthropicTokenClient {
  private readonly client: Anthropic | null;
  private readonly defaultModel: string;

  constructor(defaultModel: string, apiKey?: string) {
    this.defaultModel = defaultModel;
    const resolvedKey = apiKey || process.env.ANTHROPIC_API_KEY;
    this.client = resolvedKey ? new Anthropic({ apiKey: resolvedKey }) : null;
  }

  isReady(): boolean {
    return this.client !== null;
  }

  async countTokens(text: string, model?: string): Promise<number> {
    if (!this.client) {
      throw new Error("Anthropic API key not configured for token counting");
    }

    if (!text.trim()) {
      return 0;
    }

    const resolvedModel = model || this.defaultModel;
    console.error(
      `[TokenCounter] Calling Anthropic count_tokens (model=${resolvedModel}, chars=${text.length})`
    );

    const response: unknown = await this.client.beta.messages.countTokens({
      model: resolvedModel,
      messages: [{ role: "user", content: text }],
    });

    if (!isCountTokensResponse(response)) {
      throw new Error("Anthropic countTokens response missing input_tokens");
    }

    return response.input_tokens;
  }
}

export class OpenAITokenClient {
  private readonly encodings = new Map<string, Tiktoken>();

  isReady(): boolean {
    return true;
  }

  countTokens(text: string, model?: string): number {
    if (!text.trim()) {
      return 0;
    }

    if (!model) {
      throw new Error("OpenAI token counting requires a model name");
    }

    const encoder = this.getEncoding(model);
    const tokens = encoder.encode(text).length;
    return tokens;
  }

  private getEncoding(model: string): Tiktoken {
    const cached = this.encodings.get(model);
    if (cached) {
      return cached;
    }

    try {
      const encoding = encoding_for_model(model);
      this.encodings.set(model, encoding);
      return encoding;
    } catch {
      // Fallback: use the general-purpose cl100k_base encoding for unrecognized models
      const fallbackModelId = "cl100k_base";
      const fallback = get_encoding(fallbackModelId);
      this.encodings.set(model, fallback);
      return fallback;
    }
  }
}

export class TokenCounter implements TokenCounterLike {
  private readonly config: TokenCounterConfig;
  private readonly client: AnthropicTokenClient;
  private readonly openaiClient: OpenAITokenClient;
  private readonly cache = new Map<string, CacheEntry>();
  private calibrationSamples: number[] = [];
  private estimationErrorSamples: number[] = [];
  private estimationCharsPerToken: number;
  private metrics: TokenCounterMetrics = {
    cacheSize: 0,
    cacheHits: 0,
    cacheMisses: 0,
    anthropicCalls: 0,
    anthropicErrors: 0,
    openaiCounts: 0,
    openaiErrors: 0,
    estimationCharsPerToken: DEFAULT_CONFIG.estimationCharsPerToken,
    averageEstimationError: 0,
    calibrationSamples: 0,
    estimationSamples: 0,
    lastMode: "estimate",
  };

  constructor(
    config?: Partial<TokenCounterConfig>,
    client?: AnthropicTokenClient,
    openaiClient?: OpenAITokenClient
  ) {
    this.config = { ...DEFAULT_CONFIG, ...(config || {}) };
    this.client = client || new AnthropicTokenClient(this.config.defaultModel);
    this.openaiClient = openaiClient || new OpenAITokenClient();
    this.estimationCharsPerToken = this.config.estimationCharsPerToken;
  }

  async countExact(texts: string[], options?: TokenCountOptions): Promise<TokenCountResult> {
    const perInput: number[] = [];
    const resolvedModel = options?.model || this.config.defaultModel;
    const provider = options?.provider || "unknown";
    let cacheHits = 0;
    let cacheMisses = 0;
    let usedExactAPI = false;
    let usedOpenAI = false;

    const results = await Promise.all(
      texts.map(async (text) => {
        const normalized = text || "";
        const cacheKey = this.buildCacheKey(provider, resolvedModel, options?.baseUrl, normalized);
        const cached = this.readFromCache(cacheKey);
        if (cached !== null) {
          cacheHits++;
          return cached;
        }

        cacheMisses++;

        try {
          if (provider === "anthropic") {
            if (!this.client.isReady()) {
              throw new Error("Anthropic client unavailable");
            }

            const tokens = await this.client.countTokens(normalized, resolvedModel);
            usedExactAPI = true;
            this.metrics.anthropicCalls++;
            this.writeToCache(cacheKey, tokens);
            this.updateCalibration(normalized, tokens);
            return tokens;
          }

          if (provider === "openai") {
            if (options?.baseUrl && !options.baseUrl.includes("api.openai.com")) {
              throw new Error(
                "Custom OpenAI-compatible base URL detected; using heuristic counter"
              );
            }

            if (!options?.model) {
              throw new Error("OpenAI token counting requires the model name");
            }
            const tokens = this.openaiClient.countTokens(normalized, resolvedModel);
            usedOpenAI = true;
            this.metrics.openaiCounts++;
            this.writeToCache(cacheKey, tokens);
            this.updateCalibration(normalized, tokens);
            return tokens;
          }

          // Unknown provider: force heuristic fallback
          throw new Error(`Unsupported provider for exact token counting: ${provider}`);
        } catch (error) {
          if (provider === "anthropic") {
            this.metrics.anthropicErrors++;
          } else if (provider === "openai") {
            this.metrics.openaiErrors++;
          }
          const estimate = this.estimateSingle(normalized);
          console.warn(
            "[TokenCounter] Falling back to heuristic token estimate due to API error:",
            error
          );
          return estimate;
        }
      })
    );
    perInput.push(...results);

    const totalTokens = perInput.reduce((sum, tokens) => sum + tokens, 0);
    this.metrics.cacheHits += cacheHits;
    this.metrics.cacheMisses += cacheMisses;
    this.metrics.cacheSize = this.cache.size;
    const mode: TokenCountMode =
      usedExactAPI && this.client.isReady() ? "exact" : usedOpenAI ? "exact" : "estimate";
    this.metrics.lastMode = mode;

    return {
      mode,
      model: resolvedModel,
      totalTokens,
      perInput,
      cacheHits,
      cacheMisses,
      usedCache: cacheHits > 0,
      timestamp: Date.now(),
      estimationError: this.metrics.averageEstimationError,
    };
  }

  estimate(texts: string[], options?: TokenCountOptions): TokenCountResult {
    const perInput = texts.map((text) => this.estimateSingle(text || ""));
    const totalTokens = perInput.reduce((sum, tokens) => sum + tokens, 0);
    this.metrics.lastMode = "estimate";

    return {
      mode: "estimate",
      model: options?.model || this.config.defaultModel,
      totalTokens,
      perInput,
      cacheHits: 0,
      cacheMisses: 0,
      usedCache: false,
      timestamp: Date.now(),
      estimationError: this.metrics.averageEstimationError,
    };
  }

  collectMetrics(): TokenCounterMetrics {
    return {
      ...this.metrics,
      cacheSize: this.cache.size,
    };
  }

  private estimateSingle(text: string): number {
    if (!text) {
      return 0;
    }

    return Math.max(0, Math.ceil(text.length / this.estimationCharsPerToken));
  }

  private buildCacheKey(
    provider: string,
    model: string,
    baseUrl: string | undefined,
    text: string
  ): string {
    const hash = createHash("sha1").update(text).digest("hex");
    const endpoint = baseUrl || "default";
    return `${provider}:${endpoint}:${model}:${hash}`;
  }

  private readFromCache(key: string): number | null {
    const entry = this.cache.get(key);
    if (!entry) {
      return null;
    }

    if (entry.expiresAt < Date.now()) {
      this.cache.delete(key);
      return null;
    }

    entry.lastAccessed = Date.now();
    return entry.tokens;
  }

  private writeToCache(key: string, tokens: number): void {
    if (this.cache.size >= this.config.cacheMaxEntries) {
      let oldestKey: string | undefined;
      let oldest = Number.POSITIVE_INFINITY;
      for (const [cacheKey, entry] of this.cache.entries()) {
        if (entry.lastAccessed < oldest) {
          oldest = entry.lastAccessed;
          oldestKey = cacheKey;
        }
      }
      if (oldestKey) {
        this.cache.delete(oldestKey);
      }
    }

    this.cache.set(key, {
      tokens,
      expiresAt: Date.now() + this.config.cacheTTLms,
      lastAccessed: Date.now(),
    });
  }

  private updateCalibration(text: string, exactTokens: number): void {
    if (exactTokens <= 0 || !text.length) {
      return;
    }

    const previousEstimate = this.estimateSingle(text);
    const error = Math.abs(previousEstimate - exactTokens) / Math.max(exactTokens, 1);

    this.estimationErrorSamples.push(error);
    if (this.estimationErrorSamples.length > this.config.calibrationWindow) {
      this.estimationErrorSamples.shift();
    }

    const errorSum = this.estimationErrorSamples.reduce((sum, sample) => sum + sample, 0);
    this.metrics.averageEstimationError = errorSum / (this.estimationErrorSamples.length || 1);
    this.metrics.estimationSamples = this.estimationErrorSamples.length;

    const charsPerToken = text.length / exactTokens;
    this.calibrationSamples.push(charsPerToken);
    if (this.calibrationSamples.length > this.config.calibrationWindow) {
      this.calibrationSamples.shift();
    }

    const calibrationSum = this.calibrationSamples.reduce((sum, sample) => sum + sample, 0);
    this.estimationCharsPerToken = calibrationSum / (this.calibrationSamples.length || 1);
    this.metrics.estimationCharsPerToken = this.estimationCharsPerToken;
    this.metrics.calibrationSamples = this.calibrationSamples.length;
  }
}

let singleton: TokenCounter | null = null;

export function getTokenCounter(): TokenCounter {
  if (!singleton) {
    singleton = new TokenCounter();
  }
  return singleton;
}
