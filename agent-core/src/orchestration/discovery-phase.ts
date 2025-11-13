// agent-core/src/orchestration/discovery-phase.ts

/**
 * EP-11: Discovery Phase Orchestrator
 *
 * Implements Phase 1 of the 3-phase architect mode workflow:
 * 1. Generate strategic KB queries using Claude
 * 2. Execute queries in parallel
 * 3. Aggregate and validate results
 * 4. Enrich with graph context
 * 5. Identify information gaps
 */

import type { MCPClient } from "../mcp/client";
import type { ClaudeClient } from "../llm/claude-client";
import { KBQueryPlanner } from "../kb/kb-query-planner";
import { KBContextEnricher } from "../kb/kb-context-enricher";
import { KBResultValidator } from "../kb/kb-result-validator";
import type {
  DiscoveryConfig,
  DiscoveryQuery,
  DiscoveryResult,
  EnrichedChunk,
  GraphContext,
  ArchitectContext
} from "./types";

export class DiscoveryOrchestrator {
  private queryPlanner: KBQueryPlanner;
  private contextEnricher: KBContextEnricher;
  private resultValidator: KBResultValidator;
  private pendingDiscoveries: Map<string, Promise<DiscoveryResult>> = new Map();

  constructor(
    private mcpClient: MCPClient,
    private claudeClient: ClaudeClient,
    private config: DiscoveryConfig
  ) {
    this.queryPlanner = new KBQueryPlanner(claudeClient, {
      maxQueries: config.maxQueries,
      temperature: 0.7
    });

    this.contextEnricher = new KBContextEnricher();

    this.resultValidator = new KBResultValidator(config.confidenceThreshold);
  }

  /**
   * Execute the discovery phase with request deduplication
   */
  async execute(context: ArchitectContext): Promise<DiscoveryResult> {
    // Check if there's already a pending discovery for this query
    const cacheKey = context.userQuery;
    const pending = this.pendingDiscoveries.get(cacheKey);
    if (pending) {
      console.error(`[Discovery] Reusing pending discovery for: "${context.userQuery}"`);
      return pending;
    }

    // Create and store the discovery promise
    const discoveryPromise = this.executeDiscovery(context);
    this.pendingDiscoveries.set(cacheKey, discoveryPromise);

    // Clean up when done (both success and error cases)
    try {
      const result = await discoveryPromise;
      return result;
    } finally {
      this.pendingDiscoveries.delete(cacheKey);
    }
  }

  /**
   * Internal method that performs the actual discovery
   */
  private async executeDiscovery(context: ArchitectContext): Promise<DiscoveryResult> {
    const startTime = Date.now();

    console.error("[Discovery] Starting discovery phase...");
    console.error(`[Discovery] Query: "${context.userQuery}"`);

    // Step 1: Generate strategic queries using Claude
    const { queries, usedFallback } = await this.queryPlanner.generateQueries({
      userQuery: context.userQuery,
      conversationHistory: context.conversationHistory,
      maxQueries: this.config.maxQueries
    });

    console.error(`[Discovery] Generated ${queries.length} strategic queries`);
    queries.forEach((q, i) => {
      console.error(`[Discovery]   ${i + 1}. [${q.strategy}] "${q.text}"`);
    });

    // Step 2: Execute queries in parallel
    const searchResults = await this.executeQueriesInParallel(queries, context.repoName);

    console.error(`[Discovery] Executed ${searchResults.length} queries`);

    // Step 3: Aggregate and deduplicate results
    const aggregatedChunks = this.aggregateResults(searchResults);

    console.error(`[Discovery] Aggregated ${aggregatedChunks.length} unique chunks`);

    // Step 4: Enrich with graph context
    let graphContext: GraphContext | null = null;
    if (this.config.includeGraphContext) {
      graphContext = await this.contextEnricher.enrichWithGraph(
        aggregatedChunks,
        context.repoName
      );

      if (graphContext) {
        console.error(`[Discovery] Graph context: ${graphContext.nodes.length} nodes, ${graphContext.relationships.length} relationships`);
      }
    }

    // Step 5: Validate and score results
    const validated = await this.resultValidator.validate({
      chunks: aggregatedChunks,
      userQuery: context.userQuery,
      graphContext
    });

    console.error(`[Discovery] Validation: confidence ${(validated.overallConfidence * 100).toFixed(0)}%`);

    // Step 6: Identify gaps
    const gaps = this.resultValidator.identifyGaps(validated.chunks, context.userQuery);

    if (gaps.length > 0) {
      console.error(`[Discovery] Identified ${gaps.length} gaps:`);
      gaps.forEach(gap => console.error(`[Discovery]   - ${gap}`));
    }

    // Step 7: Generate summary
    const summary = this.generateSummary(validated.chunks, graphContext, validated.qualityMetrics, usedFallback);

    const executionTimeMs = Date.now() - startTime;
    console.error(`[Discovery] Completed in ${executionTimeMs}ms`);

    return {
      queries,
      retrievedChunks: validated.chunks,
      graphContext,
      confidence: validated.overallConfidence,
      gaps,
      summary,
      executionTimeMs
    };
  }

  /**
   * Execute all queries in parallel with timeout enforcement
   */
  private async executeQueriesInParallel(
    queries: DiscoveryQuery[],
    repoName: string
  ): Promise<KBSearchResult[]> {
    const promises = queries.map(query =>
      this.executeKBQuery(query, repoName).catch(error => {
        console.error(`[Discovery] Query failed: "${query.text}"`, error.message);
        return { hits: [] }; // Return empty result on failure
      })
    );

    // Enforce timeout
    const timeoutPromise = new Promise<KBSearchResult[]>((_, reject) =>
      setTimeout(() => reject(new Error('Discovery timeout')), this.config.timeoutMs)
    );

    try {
      return await Promise.race([Promise.all(promises), timeoutPromise]);
    } catch (error: any) {
      if (error.message === 'Discovery timeout') {
        console.error(`[Discovery] Timeout after ${this.config.timeoutMs}ms, returning partial results`);
        // Return empty results on timeout
        return queries.map(() => ({ hits: [] }));
      }
      throw error;
    }
  }

  /**
   * Execute a single KB query via MCP
   */
  private async executeKBQuery(
    query: DiscoveryQuery,
    repoName: string
  ): Promise<KBSearchResult> {
    try {
      console.error(`[Discovery] Executing query: "${query.text}" (strategy: ${query.strategy})`);

      const result = await this.mcpClient.callTool("search_knowledge", {
        query: query.text,
        repos: [repoName],
        top_k: this.config.maxResultsPerQuery,
        embed_model: "large",  // Explicitly specify to match indexed model
        include_graph_context: this.config.includeGraphContext,
        score_cutoff: this.config.confidenceThreshold
      });

      console.error(`[Discovery] Query result:`, JSON.stringify(result._meta || {}, null, 2));

      // Parse MCP result
      const parsed = this.parseMCPResult(result);
      console.error(`[Discovery] Parsed ${parsed.hits.length} hits from query: "${query.text}"`);

      return parsed;
    } catch (error: any) {
      console.error(`[Discovery] KB query failed: ${error.message}`, error);
      return { hits: [] };
    }
  }

  /**
   * Parse MCP tool result into standardized format
   */
  private parseMCPResult(result: any): KBSearchResult {
    const hits: EnrichedChunk[] = [];

    // MCP returns results in _meta.hits
    if (result._meta && Array.isArray(result._meta.hits)) {
      for (const hit of result._meta.hits) {
        // Find corresponding content block for snippet
        const resourceBlock = this.findResourceBlock(result.content, hit);

        hits.push({
          chunk_id: hit.chunk_id,
          repo: hit.repo,
          path: hit.path,
          start_line: hit.start_line,
          end_line: hit.end_line,
          language: hit.language,
          symbol_kind: hit.symbol_kind,
          symbol_name: hit.symbol_name,
          symbol_path: hit.symbol_path,
          score: hit.score,
          snippet: resourceBlock?.resource?.text || "",
          commit: hit.commit,
          branch: hit.branch,
          graph_context: hit.graph_context
        });
      }
    }

    return { hits };
  }

  /**
   * Find the resource block corresponding to a hit
   */
  private findResourceBlock(content: any[], hit: any): any {
    if (!Array.isArray(content)) return null;

    return content.find(block =>
      block.type === "resource" &&
      block.resource?.uri?.includes(hit.chunk_id)
    );
  }

  /**
   * Aggregate and deduplicate results from multiple queries
   */
  private aggregateResults(results: KBSearchResult[]): EnrichedChunk[] {
    const seen = new Set<string>();
    const aggregated: EnrichedChunk[] = [];

    for (const result of results) {
      for (const hit of result.hits) {
        if (!seen.has(hit.chunk_id)) {
          seen.add(hit.chunk_id);
          aggregated.push(hit);
        }
      }
    }

    // Sort by relevance score (descending)
    return aggregated.sort((a, b) => b.score - a.score);
  }

  /**
   * Generate a summary of discovery results
   */
  private generateSummary(
    chunks: EnrichedChunk[],
    graphContext: GraphContext | null,
    metrics: any,
    usedFallback: boolean = false
  ): string {
    const parts: string[] = [];

    parts.push(`Found ${chunks.length} relevant code chunk${chunks.length === 1 ? '' : 's'}`);

    if (chunks.length > 0) {
      const uniqueFiles = new Set(chunks.map(c => c.path)).size;
      parts.push(`across ${uniqueFiles} file${uniqueFiles === 1 ? '' : 's'}`);

      const avgScore = metrics.avgScore;
      parts.push(`(avg relevance: ${(avgScore * 100).toFixed(0)}%)`);
    }

    if (usedFallback) {
      parts.push(`(using fallback queries)`);
    }

    if (graphContext) {
      parts.push(`\nGraph context: ${graphContext.nodes.length} nodes, ${graphContext.relationships.length} relationships`);
    }

    return parts.join(" ");
  }
}

// ============================================================================
// Internal Types
// ============================================================================

interface KBSearchResult {
  hits: EnrichedChunk[];
}
