/**
 * Token bucket rate limiter for Claude API calls
 *
 * Implements rate limiting based on:
 * - Requests per minute (RPM)
 * - Input tokens per minute (TPM)
 *
 * Uses token bucket algorithm for smooth rate limiting.
 */

export interface RateLimitConfig {
  maxRequestsPerMinute: number;
  maxInputTokensPerMinute: number;
}

export interface RateLimitStatus {
  requestsAvailable: number;
  tokensAvailable: number;
  requestsUsedToday: number;
  tokensUsedToday: number;
}

export class RateLimiter {
  private requestBucket: number;
  private tokenBucket: number;
  private lastRefillTime: number;
  private requestsUsedToday: number = 0;
  private tokensUsedToday: number = 0;
  private lastResetDate: string;

  constructor(private config: RateLimitConfig) {
    this.requestBucket = config.maxRequestsPerMinute;
    this.tokenBucket = config.maxInputTokensPerMinute;
    this.lastRefillTime = Date.now();
    this.lastResetDate = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
  }

  /**
   * Refill buckets based on elapsed time
   * Token bucket algorithm: refill at rate of max_per_minute / 60 per second
   */
  private refill(): void {
    const now = Date.now();
    const elapsedMs = now - this.lastRefillTime;
    const elapsedMinutes = elapsedMs / 60000;

    // Refill request bucket
    const requestRefill = this.config.maxRequestsPerMinute * elapsedMinutes;
    this.requestBucket = Math.min(
      this.config.maxRequestsPerMinute,
      this.requestBucket + requestRefill
    );

    // Refill token bucket
    const tokenRefill = this.config.maxInputTokensPerMinute * elapsedMinutes;
    this.tokenBucket = Math.min(
      this.config.maxInputTokensPerMinute,
      this.tokenBucket + tokenRefill
    );

    this.lastRefillTime = now;

    // Reset daily counters if it's a new day
    const today = new Date().toISOString().split('T')[0];
    if (today !== this.lastResetDate) {
      this.requestsUsedToday = 0;
      this.tokensUsedToday = 0;
      this.lastResetDate = today;
    }
  }

  /**
   * Check if a request can be made with the given token count
   */
  async checkLimit(estimatedInputTokens: number = 0): Promise<{
    allowed: boolean;
    waitTimeMs: number;
    reason?: string;
  }> {
    this.refill();

    // Check if we have enough requests
    if (this.requestBucket < 1) {
      const waitTimeMs = this.calculateWaitTime(1, this.requestBucket, this.config.maxRequestsPerMinute);
      return {
        allowed: false,
        waitTimeMs,
        reason: `Rate limit: Insufficient requests (${this.requestBucket.toFixed(2)}/${this.config.maxRequestsPerMinute})`
      };
    }

    // Check if we have enough tokens
    if (estimatedInputTokens > 0 && this.tokenBucket < estimatedInputTokens) {
      const waitTimeMs = this.calculateWaitTime(
        estimatedInputTokens,
        this.tokenBucket,
        this.config.maxInputTokensPerMinute
      );
      return {
        allowed: false,
        waitTimeMs,
        reason: `Rate limit: Insufficient tokens (${this.tokenBucket.toFixed(0)}/${this.config.maxInputTokensPerMinute})`
      };
    }

    return { allowed: true, waitTimeMs: 0 };
  }

  /**
   * Reserve capacity for a request
   * Should be called before making the request
   */
  reserve(estimatedInputTokens: number = 0): void {
    this.refill();
    this.requestBucket = Math.max(0, this.requestBucket - 1);
    if (estimatedInputTokens > 0) {
      this.tokenBucket = Math.max(0, this.tokenBucket - estimatedInputTokens);
    }
  }

  /**
   * Record actual usage after request completes
   * Adjusts buckets if actual tokens differ from estimate
   */
  recordUsage(actualInputTokens: number, estimatedInputTokens: number = 0): void {
    // Adjust token bucket if actual usage differs from estimate
    const tokenDiff = estimatedInputTokens - actualInputTokens;
    this.tokenBucket = Math.min(
      this.config.maxInputTokensPerMinute,
      this.tokenBucket + tokenDiff
    );

    // Update daily counters
    this.requestsUsedToday++;
    this.tokensUsedToday += actualInputTokens;
  }

  /**
   * Get current rate limit status
   */
  getStatus(): RateLimitStatus {
    this.refill();
    return {
      requestsAvailable: Math.floor(this.requestBucket),
      tokensAvailable: Math.floor(this.tokenBucket),
      requestsUsedToday: this.requestsUsedToday,
      tokensUsedToday: this.tokensUsedToday
    };
  }

  /**
   * Calculate how long to wait before the required capacity is available
   */
  private calculateWaitTime(
    required: number,
    available: number,
    maxPerMinute: number
  ): number {
    const deficit = required - available;
    const refillRate = maxPerMinute / 60000; // per millisecond
    return Math.ceil(deficit / refillRate);
  }

  /**
   * Wait for rate limit to allow the request
   * Returns immediately if allowed, otherwise waits
   */
  async waitForCapacity(estimatedInputTokens: number = 0): Promise<void> {
    while (true) {
      const check = await this.checkLimit(estimatedInputTokens);
      if (check.allowed) {
        return;
      }

      console.error(`[RateLimiter] ${check.reason}, waiting ${check.waitTimeMs}ms...`);
      await new Promise(resolve => setTimeout(resolve, Math.min(check.waitTimeMs, 5000)));
    }
  }
}
