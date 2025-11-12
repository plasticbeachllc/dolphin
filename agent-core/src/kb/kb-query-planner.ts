// agent-core/src/kb/kb-query-planner.ts

/**
 * EP-11: KB Query Planner
 *
 * Uses Claude to generate strategic KB search queries from user requests.
 * Minimal wrapper that provides context and structure to Claude for query generation.
 */

import type { ClaudeClient } from "../llm/claude-client";
import type { DiscoveryQuery } from "../orchestration/types";
import type { Message } from "../llm/claude-tool-executor";

export interface QueryPlannerConfig {
  maxQueries: number;              // Default: 5
  temperature: number;             // Default: 0.7 (slightly creative)
}

const QUERY_GENERATION_SYSTEM_PROMPT = `You are a strategic code search query planner. Your job is to analyze a user's request and generate multiple targeted search queries that will retrieve the most relevant code from a knowledge base.

**Your Task:**
Given a user request, generate 3-5 strategic search queries with different strategies:

1. **Broad queries** - High-level concepts and patterns (e.g., "authentication middleware")
2. **Specific queries** - Exact entity names or technical terms (e.g., "JWT token validation")
3. **Pattern queries** - Common code patterns (e.g., "API endpoint decorators")
4. **Dependency queries** - Related components and imports (e.g., "database connection setup")

**Output Format:**
Return ONLY a JSON array of query objects. Each query must have:
- \`text\`: The search query string
- \`strategy\`: One of "broad", "specific", "pattern", "dependency"
- \`priority\`: Number 1-5 (1 = highest priority)
- \`expectedResultType\`: One of "function", "class", "file", "pattern", "any"

**Example:**
\`\`\`json
[
  {
    "text": "user authentication middleware",
    "strategy": "broad",
    "priority": 1,
    "expectedResultType": "any"
  },
  {
    "text": "login endpoint implementation",
    "strategy": "specific",
    "priority": 2,
    "expectedResultType": "function"
  }
]
\`\`\`

**Guidelines:**
- Prioritize queries that will find the most relevant code
- Use technical terms from the user's request
- Consider both implementation details and architectural patterns
- Avoid overly generic queries like "code" or "function"
- Each query should target different aspects of the problem`;

export class KBQueryPlanner {
  constructor(
    private claudeClient: ClaudeClient,
    private config: QueryPlannerConfig
  ) {}

  /**
   * Generate strategic KB search queries from a user request
   */
  async generateQueries(params: {
    userQuery: string;
    conversationHistory: Message[];
    maxQueries: number;
  }): Promise<{ queries: DiscoveryQuery[], usedFallback: boolean }> {
    const userPrompt = this.buildUserPrompt(params.userQuery, params.maxQueries);

    try {
      const response = await this.claudeClient.complete({
        system: QUERY_GENERATION_SYSTEM_PROMPT,
        messages: [
          ...params.conversationHistory,
          { role: "user", content: userPrompt }
        ],
        maxTokens: 1000,
        temperature: this.config.temperature,
      });

      // Parse JSON response
      const queries = this.parseQueriesFromResponse(response.content);

      // Validate and limit to maxQueries
      return {
        queries: queries.slice(0, params.maxQueries),
        usedFallback: false
      };
    } catch (error: any) {
      console.error("[KBQueryPlanner] Failed to generate queries:", error.message);

      // Fallback: Use heuristic query generation
      return {
        queries: this.generateFallbackQueries(params.userQuery, params.maxQueries),
        usedFallback: true
      };
    }
  }

  private buildUserPrompt(userQuery: string, maxQueries: number): string {
    return `# User Request

${userQuery}

# Task

Generate ${maxQueries} strategic search queries to find relevant code in the knowledge base.

Return ONLY the JSON array of queries, no additional text.`;
  }

  private parseQueriesFromResponse(content: string): DiscoveryQuery[] {
    try {
      // Extract JSON from response (handle markdown code blocks)
      let jsonText = content.trim();

      // Remove markdown code fences if present
      const jsonMatch = jsonText.match(/```(?:json)?\s*(\[[\s\S]*?\])\s*```/);
      if (jsonMatch) {
        jsonText = jsonMatch[1];
      }

      // Also handle case where JSON is not in code block
      const arrayMatch = jsonText.match(/\[[\s\S]*\]/);
      if (arrayMatch) {
        jsonText = arrayMatch[0];
      }

      const parsed = JSON.parse(jsonText);

      if (!Array.isArray(parsed)) {
        throw new Error("Response is not an array");
      }

      // Validate and transform
      return parsed.map((q: any, index: number) => ({
        text: q.text || q.query || "",
        strategy: this.validateStrategy(q.strategy),
        priority: q.priority || index + 1,
        expectedResultType: this.validateResultType(q.expectedResultType)
      })).filter(q => q.text.length > 0);
    } catch (error: any) {
      console.error("[KBQueryPlanner] Failed to parse JSON:", error.message);
      throw new Error(`Failed to parse query response: ${error.message}`);
    }
  }

  private validateStrategy(strategy: any): DiscoveryQuery["strategy"] {
    const validStrategies = ["broad", "specific", "pattern", "dependency"];
    return validStrategies.includes(strategy) ? strategy : "broad";
  }

  private validateResultType(type: any): DiscoveryQuery["expectedResultType"] {
    const validTypes = ["function", "class", "file", "pattern", "any"];
    return validTypes.includes(type) ? type : "any";
  }

  /**
   * Fallback heuristic-based query generation when Claude fails
   */
  private generateFallbackQueries(userQuery: string, maxQueries: number): DiscoveryQuery[] {
    const queries: DiscoveryQuery[] = [];

    // Query 1: Use the full user query as a broad search
    queries.push({
      text: userQuery,
      strategy: "broad",
      priority: 1,
      expectedResultType: "any"
    });

    // Query 2: Extract key technical terms (simple heuristic)
    const technicalTerms = this.extractTechnicalTerms(userQuery);
    if (technicalTerms.length > 0 && queries.length < maxQueries) {
      queries.push({
        text: technicalTerms.join(" "),
        strategy: "specific",
        priority: 2,
        expectedResultType: "any"
      });
    }

    // Query 3: Look for patterns based on keywords
    const patternQuery = this.generatePatternQuery(userQuery);
    if (patternQuery && queries.length < maxQueries) {
      queries.push({
        text: patternQuery,
        strategy: "pattern",
        priority: 3,
        expectedResultType: "pattern"
      });
    }

    return queries.slice(0, maxQueries);
  }

  private extractTechnicalTerms(query: string): string[] {
    // Simple extraction: look for capitalized words, technical keywords
    const technicalKeywords = [
      "API", "REST", "GraphQL", "HTTP", "JWT", "OAuth",
      "database", "SQL", "NoSQL", "cache", "Redis",
      "authentication", "authorization", "middleware",
      "service", "controller", "model", "view",
      "function", "class", "method", "interface"
    ];

    const words = query.toLowerCase().split(/\s+/);
    return words.filter(word =>
      technicalKeywords.some(keyword => word.includes(keyword.toLowerCase()))
    );
  }

  private generatePatternQuery(query: string): string | null {
    const lowerQuery = query.toLowerCase();

    // Pattern detection heuristics
    if (lowerQuery.includes("add") || lowerQuery.includes("implement")) {
      if (lowerQuery.includes("endpoint") || lowerQuery.includes("api")) {
        return "API endpoint pattern";
      }
      if (lowerQuery.includes("authentication") || lowerQuery.includes("auth")) {
        return "authentication middleware";
      }
    }

    return null;
  }
}
