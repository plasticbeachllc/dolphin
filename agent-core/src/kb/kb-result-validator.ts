// agent-core/src/kb/kb-result-validator.ts

/**
 * EP-11: KB Result Validator
 *
 * Validates and scores KB search results for quality and relevance.
 * Provides confidence scoring based on multiple factors.
 */

import type { EnrichedChunk, GraphContext } from "../orchestration/types";

export interface ValidationResult {
  chunks: EnrichedChunk[];
  overallConfidence: number;
  qualityMetrics: QualityMetrics;
}

export interface QualityMetrics {
  avgScore: number;
  minScore: number;
  maxScore: number;
  hasGraphContext: boolean;
  uniqueFiles: number;
  coverageScore: number;
}

export class KBResultValidator {
  private confidenceThreshold: number;

  constructor(confidenceThreshold: number = 0.05) {
    this.confidenceThreshold = confidenceThreshold;
  }

  /**
   * Validate and score search results
   */
  async validate(params: {
    chunks: EnrichedChunk[];
    userQuery: string;
    graphContext?: GraphContext | null;
  }): Promise<ValidationResult> {
    const { chunks, graphContext } = params;

    // Filter chunks by confidence threshold
    const filteredChunks = chunks.filter(chunk => chunk.score >= this.confidenceThreshold);

    // Calculate quality metrics
    const metrics = this.calculateQualityMetrics(filteredChunks, graphContext);

    // Calculate overall confidence
    const overallConfidence = this.calculateOverallConfidence(metrics);

    return {
      chunks: filteredChunks,
      overallConfidence,
      qualityMetrics: metrics
    };
  }

  /**
   * Calculate quality metrics from chunks
   */
  private calculateQualityMetrics(
    chunks: EnrichedChunk[],
    graphContext?: GraphContext | null
  ): QualityMetrics {
    if (chunks.length === 0) {
      return {
        avgScore: 0,
        minScore: 0,
        maxScore: 0,
        hasGraphContext: false,
        uniqueFiles: 0,
        coverageScore: 0
      };
    }

    // Score statistics
    const scores = chunks.map(c => c.score);
    const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;
    const minScore = Math.min(...scores);
    const maxScore = Math.max(...scores);

    // File diversity
    const uniqueFiles = new Set(chunks.map(c => c.path)).size;

    // Graph context availability
    const hasGraphContext = graphContext !== null && graphContext.nodes.length > 0;

    // Coverage score (combination of file diversity and result count)
    const coverageScore = this.calculateCoverageScore(chunks.length, uniqueFiles);

    return {
      avgScore,
      minScore,
      maxScore,
      hasGraphContext,
      uniqueFiles,
      coverageScore
    };
  }

  /**
   * Calculate coverage score (0-1) based on result count and file diversity
   */
  private calculateCoverageScore(resultCount: number, uniqueFiles: number): number {
    // Ideal: 3-10 results from 2-5 different files
    const resultScore = Math.min(resultCount / 10, 1.0);
    const diversityScore = Math.min(uniqueFiles / 5, 1.0);

    return (resultScore + diversityScore) / 2;
  }

  /**
   * Calculate overall confidence (0-1) based on quality metrics
   */
  private calculateOverallConfidence(metrics: QualityMetrics): number {
    const weights = {
      avgScore: 0.4,         // Average relevance score (40%)
      coverage: 0.3,         // Coverage score (30%)
      graphContext: 0.2,     // Graph context availability (20%)
      minScore: 0.1          // Minimum score threshold (10%)
    };

    const avgScoreComponent = metrics.avgScore * weights.avgScore;
    const coverageComponent = metrics.coverageScore * weights.coverage;
    const graphComponent = (metrics.hasGraphContext ? 1.0 : 0.5) * weights.graphContext;
    const minScoreComponent = (metrics.minScore >= this.confidenceThreshold ? 1.0 : metrics.minScore / this.confidenceThreshold) * weights.minScore;

    return Math.min(
      avgScoreComponent + coverageComponent + graphComponent + minScoreComponent,
      1.0
    );
  }

  /**
   * Identify gaps in the retrieved context
   */
  identifyGaps(chunks: EnrichedChunk[], userQuery: string): string[] {
    const gaps: string[] = [];

    if (chunks.length === 0) {
      gaps.push("No relevant code found in knowledge base");
      return gaps;
    }

    // Check for low-scoring results
    const lowScoreChunks = chunks.filter(c => c.score < 0.7);
    if (lowScoreChunks.length === chunks.length) {
      gaps.push("All results have low relevance scores - query may be too broad or specific");
    }

    // Check for missing symbol information
    const chunksWithoutSymbols = chunks.filter(c => !c.symbol_name);
    if (chunksWithoutSymbols.length > chunks.length * 0.5) {
      gaps.push("Many results lack symbol information - may include non-code content");
    }

    // Check for single-file results (might indicate limited scope)
    const uniqueFiles = new Set(chunks.map(c => c.path)).size;
    if (uniqueFiles === 1 && chunks.length > 2) {
      gaps.push("All results from single file - broader search may be needed");
    }

    // Check for missing graph context
    const hasGraphContext = chunks.some(c => c.graph_context && c.graph_context.nodes.length > 0);
    if (!hasGraphContext) {
      gaps.push("No graph context available - relationship information limited");
    }

    return gaps;
  }
}
