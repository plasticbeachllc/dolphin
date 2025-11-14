/**
 * ContextBuilder - KB Integration for Dolphin v2
 *
 * Assembles relevant context from multiple sources, with Knowledge Bank as primary source.
 *
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import { readFile } from "fs/promises";
import { PathValidator } from "../../../shared/security/path-validator";
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
}

/**
 * ContextBuilder assembles context from KB search, files, and repo maps
 */
export class ContextBuilder {
  private workspaceRoot: string;
  private kbUrl: string;

  constructor(config: ContextBuilderConfig) {
    this.workspaceRoot = config.workspaceRoot;
    this.kbUrl = config.kbUrl || "http://127.0.0.1:7777";
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

    // 1. Semantic search via KB (if query provided)
    if (params.searchQuery) {
      try {
        context.kbResults = await this.searchKnowledgeBank(params.searchQuery);
        context.totalTokens += this.estimateTokens(context.kbResults);
      } catch (error) {
        console.error("[ContextBuilder] KB search failed:", error);
        // Continue without KB results
      }
    }

    // 2. Explicitly requested files
    if (params.files && params.files.length > 0) {
      context.files = await this.loadFiles(params.files);
      context.totalTokens += this.estimateTokens(context.files);
    }

    // 3. Repo map (future feature)
    if (params.includeRepoMap) {
      // TODO: Implement repo map generation
      context.repoMap = null;
    }

    // 4. Apply token limit
    if (context.totalTokens > params.maxTokens) {
      const truncated = await this.truncateContext(context, params.maxTokens);
      context.kbResults = truncated.kbResults;
      context.files = truncated.files;
      context.repoMap = truncated.repoMap;
      context.totalTokens = truncated.totalTokens;
      context.truncated = true;
    }

    return context;
  }

  // =============================================================================
  // Private Methods
  // =============================================================================

  /**
   * Search Knowledge Bank for relevant code
   */
  private async searchKnowledgeBank(query: string): Promise<KBResult[]> {
    try {
      const response = await fetch(`${this.kbUrl}/v1/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          top_k: 20,
          diversity_threshold: 0.7,
          use_reranking: true,
        }),
      });

      if (!response.ok) {
        throw new Error(`KB search failed: ${response.statusText}`);
      }

      const results: SearchResult[] = await response.json();

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
        }))
        .sort((a, b) => b.score - a.score);
    } catch (error) {
      console.error("[ContextBuilder] KB search error:", error);
      return [];
    }
  }

  /**
   * Load files from disk
   */
  private async loadFiles(filePaths: string[]): Promise<FileContent[]> {
    const files: FileContent[] = [];
    const validator = new PathValidator({ baseDir: this.workspaceRoot });

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
  private estimateTokens(items: KBResult[] | FileContent[]): number {
    let total = 0;

    for (const item of items) {
      if ("content" in item) {
        total += this.estimateFileTokens(item.content);
      }
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
      const tokens = this.estimateFileTokens(result.content);
      if (used + tokens <= tokenBudget) {
        fitted.push(result);
        used += tokens;
      } else {
        break;
      }
    }

    return fitted;
  }
}
