/**
 * EP-11 Phase 2: Synthesis Phase
 *
 * Analyzes discovered code chunks and produces:
 * - Analysis of existing patterns and architecture
 * - Assumptions based on discovered code
 * - Clarifying questions for the user
 * - Risk assessment
 */

import type { ClaudeClient } from "../llm/claude-client";
import type {
  DiscoveryResult,
  SynthesisResult,
  EnrichedChunk,
  Assumption,
  ClarifyingQuestion,
  Risk
} from "./types";

export class SynthesisPhase {
  constructor(private claudeClient: ClaudeClient) {}

  /**
   * Synthesize discovery results into actionable analysis
   */
  async synthesize(
    userPrompt: string,
    discoveryResult: DiscoveryResult
  ): Promise<SynthesisResult> {
    console.error("[Synthesis] Starting synthesis phase...");
    console.error(`[Synthesis] Analyzing ${discoveryResult.retrievedChunks.length} code chunks`);

    // Format discovered code for Claude
    const formattedChunks = this.formatChunksForAnalysis(discoveryResult.retrievedChunks);

    // Build synthesis prompt
    const synthesisPrompt = this.buildSynthesisPrompt(
      userPrompt,
      formattedChunks,
      discoveryResult
    );

    // Get Claude's analysis (single API call)
    const response = await this.claudeClient.sendMessage({
      messages: [{ role: "user", content: synthesisPrompt }],
      model: "claude-sonnet-4-5-20250929",  // Use Sonnet for quality analysis
      maxTokens: 4000
    });

    // Parse structured response
    const synthesisResult = this.parseSynthesisResponse(response.content[0].text);

    console.error(`[Synthesis] Generated ${synthesisResult.clarifyingQuestions.length} questions`);
    console.error(`[Synthesis] Identified ${synthesisResult.risks.length} risks`);
    console.error(`[Synthesis] Confidence: ${synthesisResult.confidence}%`);

    return synthesisResult;
  }

  /**
   * Format chunks into readable code sections for Claude
   */
  private formatChunksForAnalysis(chunks: EnrichedChunk[]): string {
    if (chunks.length === 0) {
      return "<no_relevant_code_found/>";
    }

    const sections: string[] = [];

    for (const chunk of chunks) {
      sections.push(`
<code_chunk>
<location>${chunk.repo}/${chunk.path}:${chunk.start_line}-${chunk.end_line}</location>
${chunk.symbol_name ? `<symbol>${chunk.symbol_name}</symbol>` : ''}
<score>${chunk.score.toFixed(3)}</score>
\`\`\`${chunk.language || 'text'}
${chunk.snippet}
\`\`\`
</code_chunk>`);
    }

    return sections.join('\n');
  }

  /**
   * Build the synthesis prompt for Claude
   */
  private buildSynthesisPrompt(
    userPrompt: string,
    formattedChunks: string,
    discoveryResult: DiscoveryResult
  ): string {
    return `You are analyzing a codebase to help the user implement their request.

<user_request>
${userPrompt}
</user_request>

<discovery_summary>
- Confidence: ${discoveryResult.confidence}%
- Code chunks found: ${discoveryResult.retrievedChunks.length}
- Information gaps: ${discoveryResult.gaps.join(", ") || "None identified"}
</discovery_summary>

<discovered_code>
${formattedChunks}
</discovered_code>

Analyze the discovered code and produce a synthesis in this EXACT JSON format:

{
  "analysis": "1-2 paragraph analysis of relevant existing code, patterns, and architecture",
  "assumptions": [
    {
      "statement": "Clear assumption statement",
      "confidence": "high" | "medium" | "low",
      "basedOn": ["file:line references that support this"],
      "needsValidation": true | false
    }
  ],
  "clarifyingQuestions": [
    {
      "question": "Specific question for user",
      "priority": "critical" | "high" | "medium" | "low",
      "reason": "Why this matters for implementation",
      "suggestedAnswers": ["option1", "option2"]  // optional
    }
  ],
  "risks": [
    {
      "description": "Potential risk or concern",
      "severity": "high" | "medium" | "low",
      "mitigation": "Suggested mitigation approach"  // optional
    }
  ],
  "confidence": 75  // 0-100 overall confidence in understanding the request
}

Guidelines:
1. Be concise - analysis should be 1-2 paragraphs max
2. Only ask critical questions - prioritize what's absolutely needed
3. Base assumptions on actual discovered code
4. Identify risks that could derail implementation
5. Return ONLY valid JSON, no markdown formatting

Return your synthesis now:`;
  }

  /**
   * Parse Claude's JSON response into SynthesisResult
   */
  private parseSynthesisResponse(responseText: string): SynthesisResult {
    try {
      // Remove markdown code fences if present
      let jsonText = responseText.trim();
      if (jsonText.startsWith('```json')) {
        jsonText = jsonText.slice(7);
      }
      if (jsonText.startsWith('```')) {
        jsonText = jsonText.slice(3);
      }
      if (jsonText.endsWith('```')) {
        jsonText = jsonText.slice(0, -3);
      }
      jsonText = jsonText.trim();

      const parsed = JSON.parse(jsonText);

      return {
        analysis: parsed.analysis || "",
        assumptions: (parsed.assumptions || []).map((a: any) => ({
          statement: a.statement,
          confidence: a.confidence || "medium",
          basedOn: a.basedOn || [],
          needsValidation: a.needsValidation ?? false
        })),
        clarifyingQuestions: (parsed.clarifyingQuestions || []).map((q: any) => ({
          question: q.question,
          priority: q.priority || "medium",
          reason: q.reason,
          suggestedAnswers: q.suggestedAnswers
        })),
        risks: (parsed.risks || []).map((r: any) => ({
          description: r.description,
          severity: r.severity || "medium",
          mitigation: r.mitigation
        })),
        confidence: parsed.confidence || 50
      };
    } catch (error) {
      console.error("[Synthesis] Failed to parse JSON response:", error);
      console.error("[Synthesis] Raw response:", responseText);

      // Fallback: return basic result
      return {
        analysis: responseText,
        assumptions: [],
        clarifyingQuestions: [],
        risks: [],
        confidence: 30
      };
    }
  }
}
