/**
 * ContextBuilder - KB Integration for Dolphin v2
 *
 * Assembles relevant context from multiple sources, with Knowledge Bank as primary source.
 *
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import { existsSync } from "fs";
import { readFile } from "fs/promises";
import { PathValidator } from "../../../shared/security/path-validator";
import type { TokenCountOptions, TokenCounterLike } from "../utils/token-counter.js";
import { getTokenCounter } from "../utils/token-counter.js";
import type {
  Context,
  ContextBuildParams,
  KBResult,
  FileContent,
  SearchResult,
} from "../types/index.js";

/**
 * Configuration for ContextBuilder
 */
export interface ContextBuilderConfig {
  workspaceRoot: string;
  kbUrl?: string;
  kbTimeoutMs?: number;
  tokenCounter?: TokenCounterLike;
  kbApiKey?: string;
}

/**
 * ContextBuilder assembles context from KB search, files, and repo maps
 */
export class ContextBuilder {
  private workspaceRoot: string;
  private kbUrl: string;
  private kbTimeoutMs: number;
  private tokenCounter: TokenCounterLike;
  private kbApiKey?: string;

  constructor(config: ContextBuilderConfig) {
    this.workspaceRoot = config.workspaceRoot;
    this.kbUrl = config.kbUrl || "http://127.0.0.1:7777";
    this.kbTimeoutMs = config.kbTimeoutMs ?? 2000;
    this.tokenCounter = config.tokenCounter ?? getTokenCounter();
    this.kbApiKey =
      config.kbApiKey || process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY || undefined;
  }

  /**
   * Build context for a task
   */
  async build(params: ContextBuildParams): Promise<Context> {
    const context: Context = {
      kbResults: [],
      files: [],
      repoMap: null,
      totalTokens: 0,
      truncated: false,
    };

    const tokenOptions = params.tokenContext
      ? {
          model: params.tokenContext.model,
          provider: params.tokenContext.provider,
          baseUrl: params.tokenContext.baseUrl,
        }
      : undefined;

    // 1. Semantic search via KB (if query provided)
    if (params.searchQuery) {
      try {
        context.kbResults = await this.searchKnowledgeBank(params.searchQuery);
      } catch (error) {
        console.error("[ContextBuilder] KB search failed:", error);
        // Continue without KB results
      }
    }

    // 2. Explicitly requested files
    if (params.files && params.files.length > 0) {
      context.files = await this.loadFiles(params.files);
    }

    // 3. Repo map (future feature)
    if (params.includeRepoMap) {
      // TODO: Implement repo map generation
      context.repoMap = null;
    }

    context.totalTokens =
      this.estimateTokens(context.kbResults) + this.estimateTokens(context.files);

    // 4. Apply token limit
    if (context.totalTokens > params.maxTokens) {
      const truncated = await this.truncateContext(context, params.maxTokens);
      context.kbResults = truncated.kbResults;
      context.files = truncated.files;
      context.repoMap = truncated.repoMap;
      context.totalTokens = truncated.totalTokens;
      context.truncated = true;
    }

    await this.reconcileTokenCounts(context, tokenOptions);

    return context;
  }

  // =============================================================================
  // Private Methods
  // =============================================================================

  /**
   * Search Knowledge Bank for relevant code
   */
  private async searchKnowledgeBank(query: string): Promise<KBResult[]> {
    const controller = new AbortController();
    const timeoutHandle = setTimeout(() => controller.abort(), this.kbTimeoutMs);

    try {
      const response = await fetch(`${this.kbUrl.replace(/\/$/, "")}/v1/search`, {
        method: "POST",
        headers: this.buildHeaders(),
        body: JSON.stringify({
          query,
          top_k: 20,
          diversity_threshold: 0.7,
          use_reranking: true,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`KB search failed: ${response.statusText}`);
      }

      const results = (await response.json()) as SearchResult[];

      // Transform to KBResult format and sort by score (descending)
      return results
        .map((r) => ({
          file: r.file_path,
          startLine: r.start_line,
          endLine: r.end_line,
          content: r.snippet_text,
          language: r.language,
          score: r.score,
          chunkId: r.chunk_id,
          tokens: this.estimateFileTokens(r.snippet_text),
        }))
        .sort((a, b) => b.score - a.score);
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        console.warn(
          `[ContextBuilder] KB search timed out after ${this.kbTimeoutMs}ms while querying '${query}'`
        );
      } else {
        console.error("[ContextBuilder] KB search error:", error);
      }
      return [];
    } finally {
      clearTimeout(timeoutHandle);
    }
  }

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.kbApiKey) {
      headers["X-API-Key"] = this.kbApiKey;
    }
    return headers;
  }

  /**
   * Load files from disk
   */
  private async loadFiles(filePaths: string[]): Promise<FileContent[]> {
    const files: FileContent[] = [];

    if (!existsSync(this.workspaceRoot)) {
      console.warn(
        `[ContextBuilder] Workspace root '${this.workspaceRoot}' not found. Skipping explicit file loads.`
      );
      return files;
    }

    let validator: PathValidator;
    try {
      validator = new PathValidator({ baseDir: this.workspaceRoot });
    } catch (error) {
      console.error(
        `[ContextBuilder] Failed to initialize path validator for '${this.workspaceRoot}':`,
        error
      );
      return files;
    }

    for (const path of filePaths) {
      try {
        // Validate path to prevent directory traversal attacks
        const fullPath = validator.validate(path);
        const content = await readFile(fullPath, "utf-8");
        const language = this.detectLanguage(path);
        const tokens = this.estimateFileTokens(content);

        files.push({
          path,
          content,
          language,
          tokens,
        });
      } catch (error) {
        console.error(`[ContextBuilder] Failed to load file ${path}:`, error);
        // Continue with other files
      }
    }

    return files;
  }

  /**
   * Detect language from file extension
   */
  private detectLanguage(filePath: string): string {
    const ext = filePath.split(".").pop()?.toLowerCase();

    const languageMap: Record<string, string> = {
      ts: "typescript",
      tsx: "typescript",
      js: "javascript",
      jsx: "javascript",
      py: "python",
      go: "go",
      rs: "rust",
      java: "java",
      c: "c",
      cpp: "cpp",
      h: "c",
      hpp: "cpp",
      cs: "csharp",
      rb: "ruby",
      php: "php",
      swift: "swift",
      kt: "kotlin",
      scala: "scala",
      sh: "bash",
      md: "markdown",
      json: "json",
      yaml: "yaml",
      yml: "yaml",
      toml: "toml",
      xml: "xml",
      html: "html",
      css: "css",
      scss: "scss",
      sql: "sql",
    };

    return languageMap[ext || ""] || "text";
  }

  /**
   * Estimate tokens for KB results
   */
  private estimateTokens(items: Array<KBResult | FileContent>): number {
    let total = 0;

    for (const item of items) {
      const tokens =
        typeof item.tokens === "number" ? item.tokens : this.estimateFileTokens(item.content);
      total += tokens;
    }

    return total;
  }

  /**
   * Estimate tokens for file content
   */
  private estimateFileTokens(content: string): number {
    // Rough estimate: 1 token ≈ 4 characters
    return Math.ceil(content.length / 4);
  }

  /**
   * Truncate context to fit within token budget
   */
  private async truncateContext(context: Context, maxTokens: number): Promise<Context> {
    // Strategy: Prioritize explicitly requested files > KB results > repo map
    let remaining = maxTokens;
    const truncated = { ...context };

    // 1. Keep all explicitly requested files (high priority)
    const fileTokens = this.estimateTokens(truncated.files);
    remaining -= fileTokens;

    // 2. Trim KB results if needed
    if (remaining < 0) {
      // Need to cut files - take top N by importance
      const filesWithPriority = this.prioritizeFiles(truncated.files);
      truncated.files = this.fitFilesInBudget(filesWithPriority, maxTokens * 0.7);
      remaining = maxTokens - this.estimateTokens(truncated.files);
    }

    // 3. Add KB results up to remaining budget
    const kbResultsInBudget = this.fitKBResultsInBudget(truncated.kbResults, remaining);
    truncated.kbResults = kbResultsInBudget;

    // 4. Drop repo map if out of budget (lowest priority)
    const totalUsed =
      this.estimateTokens(truncated.files) + this.estimateTokens(truncated.kbResults);
    if (totalUsed > maxTokens) {
      truncated.repoMap = null;
    }

    truncated.totalTokens = totalUsed;

    return truncated;
  }

  /**
   * Prioritize files by importance
   */
  private prioritizeFiles(files: FileContent[]): FileContent[] {
    // For now, keep original order
    // Future: implement smart prioritization based on file type, size, etc.
    return [...files];
  }

  /**
   * Fit files within token budget
   */
  private fitFilesInBudget(files: FileContent[], tokenBudget: number): FileContent[] {
    const fitted: FileContent[] = [];
    let used = 0;

    for (const file of files) {
      if (used + file.tokens <= tokenBudget) {
        fitted.push(file);
        used += file.tokens;
      } else {
        break;
      }
    }

    return fitted;
  }

  /**
   * Fit KB results within token budget
   */
  private fitKBResultsInBudget(results: KBResult[], tokenBudget: number): KBResult[] {
    // Sort by score (best results first)
    const sorted = [...results].sort((a, b) => b.score - a.score);

    const fitted: KBResult[] = [];
    let used = 0;

    for (const result of sorted) {
      const tokens = result.tokens ?? this.estimateFileTokens(result.content);
      if (used + tokens <= tokenBudget) {
        fitted.push({ ...result, tokens });
        used += tokens;
      } else {
        break;
      }
    }

    return fitted;
  }

  private async reconcileTokenCounts(
    context: Context,
    tokenOptions?: TokenCountOptions
  ): Promise<void> {
    const fileContents = context.files.map((file) => file.content);
    const kbContents = context.kbResults.map((result) => result.content);
    let totalTokens = 0;

    try {
      if (fileContents.length) {
        const result = await this.tokenCounter.countExact(fileContents, tokenOptions);
        context.files = context.files.map((file, index) => ({
          ...file,
          tokens: result.perInput[index] ?? file.tokens ?? this.estimateFileTokens(file.content),
        }));
        totalTokens += result.totalTokens;
      }

      if (kbContents.length) {
        const result = await this.tokenCounter.countExact(kbContents, tokenOptions);
        context.kbResults = context.kbResults.map((kbResult, index) => ({
          ...kbResult,
          tokens:
            result.perInput[index] ?? kbResult.tokens ?? this.estimateFileTokens(kbResult.content),
        }));
        totalTokens += result.totalTokens;
      }
    } catch (error) {
      console.warn("[ContextBuilder] Failed to compute exact token counts:", error);
      totalTokens = this.estimateTokens(context.kbResults) + this.estimateTokens(context.files);
    }

    context.totalTokens = totalTokens;
  }
}
