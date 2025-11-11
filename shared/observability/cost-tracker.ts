/**
 * Cost tracking for Claude API and embedding usage.
 * Provides real-time cost monitoring and budget enforcement.
 */

import { createLogger } from './logger';

const logger = createLogger('cost-tracker');

/**
 * Pricing configuration (as of November 2025).
 */
export const PRICING = {
  'claude-sonnet-4.5': {
    input: 3.0 / 1_000_000, // $3 per 1M input tokens
    output: 15.0 / 1_000_000, // $15 per 1M output tokens
  },
  'claude-opus': {
    input: 15.0 / 1_000_000,
    output: 75.0 / 1_000_000,
  },
  'claude-haiku': {
    input: 0.25 / 1_000_000,
    output: 1.25 / 1_000_000,
  },
  'text-embedding-3-small': {
    tokens: 0.02 / 1_000_000, // $0.02 per 1M tokens
  },
  'text-embedding-3-large': {
    tokens: 0.13 / 1_000_000, // $0.13 per 1M tokens
  },
};

export interface CostSummary {
  claudeApiCost: number;
  embeddingCost: number;
  totalCost: number;
  projectedDailyCost: number;
}

export interface BudgetConfig {
  dailyLimit: number;
  warningThreshold: number; // percentage (0-1)
  blockThreshold: number; // percentage (0-1)
}

const DEFAULT_BUDGET_CONFIG: BudgetConfig = {
  dailyLimit: 100.0, // $100/day
  warningThreshold: 0.8, // Warn at 80%
  blockThreshold: 0.95, // Block at 95%
};

/**
 * Cost tracker for a single session.
 */
export class CostTracker {
  private costs = {
    claude: 0,
    embeddings: 0,
  };

  private readonly sessionStart = Date.now();
  private readonly budgetConfig: BudgetConfig;
  private warningIssued = false;

  constructor(budgetConfig: Partial<BudgetConfig> = {}) {
    this.budgetConfig = { ...DEFAULT_BUDGET_CONFIG, ...budgetConfig };
  }

  /**
   * Record Claude API token usage and cost.
   */
  recordClaudeTokens(model: string, inputTokens: number, outputTokens: number): number {
    const pricing = PRICING[model as keyof typeof PRICING];
    if (!pricing || !('input' in pricing)) {
      logger.warn('Unknown Claude model for cost tracking', { model });
      return 0;
    }

    const cost = inputTokens * pricing.input + outputTokens * pricing.output;
    this.costs.claude += cost;

    logger.debug('Recorded Claude API cost', {
      model,
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      cost_usd: cost,
    });

    return cost;
  }

  /**
   * Record embedding token usage and cost.
   */
  recordEmbeddingTokens(model: string, tokens: number): number {
    const pricing = PRICING[model as keyof typeof PRICING];
    if (!pricing || !('tokens' in pricing)) {
      logger.warn('Unknown embedding model for cost tracking', { model });
      return 0;
    }

    const cost = tokens * pricing.tokens;
    this.costs.embeddings += cost;

    logger.debug('Recorded embedding cost', {
      model,
      tokens,
      cost_usd: cost,
    });

    return cost;
  }

  /**
   * Get current cost summary.
   */
  getCurrentCost(): CostSummary {
    const totalCost = this.costs.claude + this.costs.embeddings;

    // Project to daily cost based on elapsed time
    const elapsedHours = (Date.now() - this.sessionStart) / (1000 * 60 * 60);
    const projectedDailyCost = elapsedHours > 0 ? (totalCost / elapsedHours) * 24 : 0;

    return {
      claudeApiCost: this.costs.claude,
      embeddingCost: this.costs.embeddings,
      totalCost,
      projectedDailyCost,
    };
  }

  /**
   * Check if within budget.
   */
  checkBudget(): { allowed: boolean; reason?: string; warning?: string } {
    const cost = this.getCurrentCost();
    const percentage = cost.projectedDailyCost / this.budgetConfig.dailyLimit;

    // Block if over threshold
    if (percentage >= this.budgetConfig.blockThreshold) {
      logger.error('Budget exceeded', undefined, {
        projected_cost: cost.projectedDailyCost,
        limit: this.budgetConfig.dailyLimit,
        percentage: percentage * 100,
      });

      return {
        allowed: false,
        reason: `Projected daily cost ($${cost.projectedDailyCost.toFixed(2)}) exceeds budget ($${this.budgetConfig.dailyLimit})`,
      };
    }

    // Warn if approaching limit
    if (percentage >= this.budgetConfig.warningThreshold && !this.warningIssued) {
      logger.warn('Approaching budget limit', {
        projected_cost: cost.projectedDailyCost,
        limit: this.budgetConfig.dailyLimit,
        percentage: percentage * 100,
      });

      this.warningIssued = true;

      return {
        allowed: true,
        warning: `Approaching budget limit: $${cost.projectedDailyCost.toFixed(2)} / $${this.budgetConfig.dailyLimit}`,
      };
    }

    return { allowed: true };
  }

  /**
   * Reset costs (for testing or new session).
   */
  reset(): void {
    this.costs.claude = 0;
    this.costs.embeddings = 0;
    this.warningIssued = false;
  }
}

/**
 * Global cost tracker instance.
 */
let globalTracker: CostTracker | null = null;

/**
 * Get or create the global cost tracker.
 */
export function getGlobalCostTracker(budgetConfig?: Partial<BudgetConfig>): CostTracker {
  if (!globalTracker) {
    globalTracker = new CostTracker(budgetConfig);
  }
  return globalTracker;
}

/**
 * Reset the global cost tracker.
 */
export function resetGlobalCostTracker(): void {
  globalTracker = null;
}
