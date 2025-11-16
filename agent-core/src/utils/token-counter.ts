import Anthropic from "@anthropic-ai/sdk";
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

export interface TokenCounterMetrics {
  cacheSize: number;
  cacheHits: number;
  cacheMisses: number;
  anthropicCalls: number;
  anthropicErrors: number;
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

export interface TokenCounterLike {
  countExact(texts: string[], model?: string): Promise<TokenCountResult>;
  estimate(texts: string[], model?: string): TokenCountResult;
  collectMetrics(): TokenCounterMetrics;
}

const DEFAULT_CONFIG: TokenCounterConfig = {
  defaultModel: "claude-sonnet-4-20250514",
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

    const response = await this.client.messages.countTokens({
      model: resolvedModel,
      messages: [{ role: "user", content: text }],
    });

    return response.input_tokens;
  }
}

export class TokenCounter implements TokenCounterLike {
  private readonly config: TokenCounterConfig;
  private readonly client: AnthropicTokenClient;
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
    estimationCharsPerToken: DEFAULT_CONFIG.estimationCharsPerToken,
    averageEstimationError: 0,
    calibrationSamples: 0,
    estimationSamples: 0,
    lastMode: "estimate",
  };

  constructor(config?: Partial<TokenCounterConfig>, client?: AnthropicTokenClient) {
    this.config = { ...DEFAULT_CONFIG, ...(config || {}) };
    this.client = client || new AnthropicTokenClient(this.config.defaultModel);
    this.estimationCharsPerToken = this.config.estimationCharsPerToken;
  }

  async countExact(texts: string[], model?: string): Promise<TokenCountResult> {
    const perInput: number[] = [];
    const resolvedModel = model || this.config.defaultModel;
    let cacheHits = 0;
    let cacheMisses = 0;
    let usedExactAPI = false;

    for (const text of texts) {
      const normalized = text || "";
      const cacheKey = this.buildCacheKey(resolvedModel, normalized);
      const cached = this.readFromCache(cacheKey);
      if (cached !== null) {
        cacheHits++;
        perInput.push(cached);
        continue;
      }

      cacheMisses++;

      try {
        if (!this.client.isReady()) {
          throw new Error("Anthropic client unavailable");
        }

        const tokens = await this.client.countTokens(normalized, resolvedModel);
        usedExactAPI = true;
        perInput.push(tokens);
        this.metrics.anthropicCalls++;
        this.writeToCache(cacheKey, tokens);
        this.updateCalibration(normalized, tokens);
      } catch (error) {
        this.metrics.anthropicErrors++;
        const estimate = this.estimateSingle(normalized);
        perInput.push(estimate);
        console.warn(
          "[TokenCounter] Falling back to heuristic token estimate due to API error:",
          error
        );
      }
    }

    const totalTokens = perInput.reduce((sum, tokens) => sum + tokens, 0);
    this.metrics.cacheHits += cacheHits;
    this.metrics.cacheMisses += cacheMisses;
    this.metrics.cacheSize = this.cache.size;
    const mode: TokenCountMode = usedExactAPI && this.client.isReady() ? "exact" : "estimate";
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

  estimate(texts: string[], model?: string): TokenCountResult {
    const perInput = texts.map((text) => this.estimateSingle(text || ""));
    const totalTokens = perInput.reduce((sum, tokens) => sum + tokens, 0);
    this.metrics.lastMode = "estimate";

    return {
      mode: "estimate",
      model: model || this.config.defaultModel,
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

  private buildCacheKey(model: string, text: string): string {
    const hash = createHash("sha1").update(text).digest("hex");
    return `${model}:${hash}`;
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
    this.metrics.averageEstimationError =
      errorSum / (this.estimationErrorSamples.length || 1);
    this.metrics.estimationSamples = this.estimationErrorSamples.length;

    const charsPerToken = text.length / exactTokens;
    this.calibrationSamples.push(charsPerToken);
    if (this.calibrationSamples.length > this.config.calibrationWindow) {
      this.calibrationSamples.shift();
    }

    const calibrationSum = this.calibrationSamples.reduce((sum, sample) => sum + sample, 0);
    this.estimationCharsPerToken =
      calibrationSum / (this.calibrationSamples.length || 1);
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
