# EP-11: Architect Mode KB Discovery Enhancement Plan

**Version**: 1.0  
**Date**: November 11, 2025  
**Status**: Planning Phase  
**Timeline**: 3-4 weeks  

---

## Executive Summary

### Current State

Architect mode currently has **optional** Knowledge Bank (KB) integration:
- Manual KB search only when authentication fails
- No systematic discovery phase
- KB results appended as context but not enforced
- Agent orchestration relies primarily on Claude's internal knowledge
- No structured information gathering workflow

### Problem Statement

Architect mode lacks a **mandatory discovery phase** that:
1. **Systematically searches KB** for relevant codebase context before planning
2. **Enforces semantic understanding** of existing code patterns and architecture
3. **Prevents hallucination** by grounding responses in actual codebase
4. **Improves plan quality** through better context awareness
5. **Leverages graph intelligence** (from EP-3) for relationship discovery

### Proposed Solution

Implement a **3-phase orchestration workflow** for architect mode:

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: DISCOVERY (NEW - Mandatory KB Search)             │
│  • Multi-query KB search with strategic query generation   │
│  • Graph-aware context enrichment                           │
│  • Dependency and relationship mapping                      │
│  • Confidence scoring for retrieved context                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: SYNTHESIS (Enhanced with KB Context)              │
│  • Analyze user request + KB context                        │
│  • Identify gaps in understanding                           │
│  • Generate clarifying questions                            │
│  • Validate assumptions against codebase                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: PLANNING (Context-Grounded)                       │
│  • Generate implementation plan                             │
│  • Reference specific files/functions from KB               │
│  • Identify affected components via graph                   │
│  • Create todo list with concrete file references           │
└─────────────────────────────────────────────────────────────┘
```

### Success Metrics

- **Discovery Phase Execution**: 100% of architect mode requests trigger KB search
- **Context Quality**: 80%+ of plans reference actual codebase entities
- **Hallucination Reduction**: 90% reduction in recommendations for non-existent code
- **User Satisfaction**: Improved plan relevance and actionability
- **Performance**: <3s for discovery phase (including multiple KB queries)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Detailed Design](#detailed-design)
3. [Implementation Phases](#implementation-phases)
4. [API Specifications](#api-specifications)
5. [Testing Strategy](#testing-strategy)
6. [Migration Plan](#migration-plan)
7. [Success Metrics & KPIs](#success-metrics--kpis)
8. [Risk Mitigation](#risk-mitigation)
9. [Future Enhancements](#future-enhancements)

---

## Architecture Overview

### Current Flow (Simplified)

```typescript
// agent-core/src/main.ts - Current handleSendMessage
if (authStatus.mode === "api_key" || authStatus.mode === "claude_cli") {
  // Agentic tool loop - Claude decides if/when to use KB
  const result = await this.toolExecutor.executeWithTools(
    request.content,
    this.conversationHistory
  );
} else {
  // Manual orchestration - KB search happens ONCE if no auth
  const kbResult = await this.mcpClient.callTool("search_knowledge", {
    query: request.content,
    top_k: 3
  });
  
  await this.planner.processMessage({
    userMessage: request.content,
    kbResults: kbContext
  });
}
```

**Problems:**
- KB search is **optional** and **single-pass**
- No strategic query planning
- No graph-aware context enrichment
- No validation of retrieved context quality

### Proposed Flow (Enhanced)

```typescript
// New orchestration flow for architect mode
if (request.mode === "architect") {
  // Phase 1: DISCOVERY (NEW - Mandatory)
  const discoveryResult = await this.discoveryOrchestrator.execute({
    userQuery: request.content,
    workspaceRoot: this.workspaceRoot,
    repoName: this.repoName,
    conversationHistory: this.conversationHistory
  });
  
  // Phase 2: SYNTHESIS (Enhanced)
  const synthesisResult = await this.synthesisOrchestrator.analyze({
    userQuery: request.content,
    discoveredContext: discoveryResult,
    conversationHistory: this.conversationHistory
  });
  
  // Phase 3: PLANNING (Context-Grounded)
  const plan = await this.planningOrchestrator.generate({
    userQuery: request.content,
    discoveryContext: discoveryResult,
    synthesisInsights: synthesisResult,
    conversationHistory: this.conversationHistory
  });
  
  // Present plan to user
  this.sendEvent({ type: "plan_ready", plan });
}
```

### Component Architecture

```
agent-core/src/
├── orchestration/
│   ├── architect-orchestrator.ts        # Main orchestrator for architect mode
│   ├── discovery-phase.ts               # Phase 1: KB discovery logic
│   ├── synthesis-phase.ts               # Phase 2: Analysis & questions
│   ├── planning-phase.ts                # Phase 3: Plan generation
│   └── types.ts                         # Shared types
├── kb/
│   ├── kb-query-planner.ts             # Strategic query generation
│   ├── kb-context-enricher.ts          # Graph-aware enrichment
│   ├── kb-result-validator.ts          # Quality scoring
│   └── kb-context-aggregator.ts        # Result aggregation
└── llm/
    ├── architect-prompts.ts            # Specialized prompts
    └── streaming-synthesizer.ts       # Streaming synthesis
```

---

## Detailed Design

### Phase 1: Discovery Orchestrator

#### Responsibilities

1. **Query Strategy Generation**
   - Analyze user request to identify information needs
   - Generate multiple strategic KB queries
   - Prioritize queries by expected value

2. **Multi-Query Execution**
   - Execute KB searches in parallel
   - Apply different search strategies (broad vs. specific)
   - Include graph context when available

3. **Result Validation & Scoring**
   - Assess relevance and confidence of results
   - Identify gaps in retrieved context
   - Flag potentially missing information

4. **Context Aggregation**
   - Deduplicate and merge results
   - Build coherent context narrative
   - Maintain source attribution

#### Implementation

```typescript
// agent-core/src/orchestration/discovery-phase.ts

export interface DiscoveryConfig {
  maxQueries: number;              // Default: 5
  maxResultsPerQuery: number;      // Default: 5
  includeGraphContext: boolean;    // Default: true
  confidenceThreshold: number;     // Default: 0.6
  timeoutMs: number;               // Default: 5000
}

export interface DiscoveryQuery {
  text: string;
  strategy: "broad" | "specific" | "pattern" | "dependency";
  priority: number;
  expectedResultType: "function" | "class" | "file" | "pattern" | "any";
}

export interface DiscoveryResult {
  queries: DiscoveryQuery[];
  retrievedChunks: EnrichedChunk[];
  graphContext: GraphContext | null;
  confidence: number;
  gaps: string[];                  // Identified information gaps
  summary: string;
  executionTimeMs: number;
}

export class DiscoveryOrchestrator {
  constructor(
    private mcpClient: MCPClient,
    private queryPlanner: KBQueryPlanner,
    private contextEnricher: KBContextEnricher,
    private resultValidator: KBResultValidator,
    private config: DiscoveryConfig
  ) {}
  
  async execute(params: {
    userQuery: string;
    workspaceRoot: string;
    repoName: string;
    conversationHistory: Message[];
  }): Promise<DiscoveryResult> {
    const startTime = Date.now();
    
    // Step 1: Generate strategic queries
    const queries = await this.queryPlanner.generateQueries({
      userQuery: params.userQuery,
      conversationHistory: params.conversationHistory,
      maxQueries: this.config.maxQueries
    });
    
    console.error(`[Discovery] Generated ${queries.length} strategic queries`);
    
    // Step 2: Execute queries in parallel
    const searchResults = await Promise.all(
      queries.map(query => this.executeKBQuery(query, params.repoName))
    );
    
    // Step 3: Aggregate and deduplicate results
    const aggregatedChunks = this.aggregateResults(searchResults);
    
    // Step 4: Enrich with graph context if available
    let graphContext: GraphContext | null = null;
    if (this.config.includeGraphContext) {
      graphContext = await this.contextEnricher.enrichWithGraph(
        aggregatedChunks,
        params.repoName
      );
    }
    
    // Step 5: Validate and score results
    const validated = await this.resultValidator.validate({
      chunks: aggregatedChunks,
      userQuery: params.userQuery,
      graphContext
    });
    
    // Step 6: Identify gaps
    const gaps = this.identifyGaps(params.userQuery, validated.chunks);
    
    // Step 7: Generate summary
    const summary = this.generateSummary(validated.chunks, graphContext);
    
    return {
      queries,
      retrievedChunks: validated.chunks,
      graphContext,
      confidence: validated.overallConfidence,
      gaps,
      summary,
      executionTimeMs: Date.now() - startTime
    };
  }
  
  private async executeKBQuery(
    query: DiscoveryQuery,
    repoName: string
  ): Promise<KBSearchResult> {
    return await this.mcpClient.callTool("search_knowledge", {
      query: query.text,
      repos: [repoName],
      top_k: this.config.maxResultsPerQuery,
      include_graph_context: this.config.includeGraphContext,
      score_cutoff: this.config.confidenceThreshold
    });
  }
  
  private aggregateResults(
    results: KBSearchResult[]
  ): EnrichedChunk[] {
    // Deduplicate by chunk_id
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
    
    // Sort by relevance score
    return aggregated.sort((a, b) => b.score - a.score);
  }
  
  private identifyGaps(
    userQuery: string,
    chunks: EnrichedChunk[]
  ): string[] {
    const gaps: string[] = [];
    
    // Heuristics for gap detection
    if (chunks.length === 0) {
      gaps.push("No relevant code found in knowledge base");
    }
    
    // TODO: More sophisticated gap detection
    // - Missing file types (e.g., "needs tests but none found")
    // - Missing dependencies (e.g., "references module X but not found")
    // - Low confidence scores
    
    return gaps;
  }
  
  private generateSummary(
    chunks: EnrichedChunk[],
    graphContext: GraphContext | null
  ): string {
    const parts: string[] = [];
    
    parts.push(`Found ${chunks.length} relevant code chunks`);
    
    if (graphContext) {
      parts.push(
        `Graph context: ${graphContext.nodes.length} nodes, ` +
        `${graphContext.edges.length} relationships`
      );
    }
    
    const files = new Set(chunks.map(c => c.path));
    parts.push(`Across ${files.size} files`);
    
    return parts.join(". ");
  }
}
```

### Phase 2: Synthesis Orchestrator

#### Responsibilities

1. **Context Analysis**
   - Integrate user query with discovered context
   - Identify assumptions and uncertainties
   - Detect potential misunderstandings

2. **Question Generation**
   - Generate clarifying questions based on gaps
   - Prioritize questions by importance
   - Frame questions to maximize information gain

3. **Validation**
   - Check assumptions against codebase facts
   - Flag contradictions or inconsistencies
   - Provide confidence levels

#### Implementation

```typescript
// agent-core/src/orchestration/synthesis-phase.ts

export interface SynthesisResult {
  analysis: string;
  assumptions: Assumption[];
  clarifyingQuestions: ClarifyingQuestion[];
  risks: Risk[];
  confidence: number;
}

export interface Assumption {
  statement: string;
  confidence: "high" | "medium" | "low";
  basedOn: string[];  // Source attributions
  needsValidation: boolean;
}

export interface ClarifyingQuestion {
  question: string;
  priority: "critical" | "high" | "medium" | "low";
  reason: string;
  suggestedAnswers?: string[];
}

export class SynthesisOrchestrator {
  constructor(
    private claudeClient: ClaudeClient,
    private config: { maxTokens: number; temperature: number }
  ) {}
  
  async analyze(params: {
    userQuery: string;
    discoveredContext: DiscoveryResult;
    conversationHistory: Message[];
  }): Promise<SynthesisResult> {
    const prompt = this.buildSynthesisPrompt(params);
    
    const response = await this.claudeClient.complete({
      system: SYNTHESIS_SYSTEM_PROMPT,
      messages: [
        ...params.conversationHistory,
        { role: "user", content: prompt }
      ],
      maxTokens: this.config.maxTokens,
      temperature: this.config.temperature
    });
    
    // Parse structured response
    return this.parseResponse(response.content);
  }
  
  private buildSynthesisPrompt(params: {
    userQuery: string;
    discoveredContext: DiscoveryResult;
  }): string {
    return `# User Request
${params.userQuery}

# Discovered Codebase Context
${this.formatDiscoveryContext(params.discoveredContext)}

# Your Task
Analyze the user's request in light of the discovered codebase context:

1. **Analysis**: Summarize what you understand about the request and existing codebase
2. **Assumptions**: List any assumptions you're making, with confidence levels
3. **Clarifying Questions**: Generate questions to fill gaps in understanding
4. **Risks**: Identify potential risks or concerns based on the codebase

Format your response as JSON matching the SynthesisResult interface.`;
  }
  
  private formatDiscoveryContext(discovery: DiscoveryResult): string {
    const parts: string[] = [];
    
    parts.push(`## Summary\n${discovery.summary}`);
    parts.push(`## Confidence: ${(discovery.confidence * 100).toFixed(0)}%`);
    
    if (discovery.gaps.length > 0) {
      parts.push(`## Information Gaps\n${discovery.gaps.map(g => `- ${g}`).join('\n')}`);
    }
    
    parts.push(`## Retrieved Code Context`);
    for (const chunk of discovery.retrievedChunks.slice(0, 10)) {
      parts.push(`\n### ${chunk.repo}/${chunk.path}#L${chunk.start_line}-L${chunk.end_line}`);
      if (chunk.symbol_name) {
        parts.push(`**Symbol**: ${chunk.symbol_name} (${chunk.symbol_kind})`);
      }
      parts.push(`**Score**: ${chunk.score.toFixed(2)}`);
      parts.push(`\`\`\`${chunk.language}\n${chunk.snippet}\n\`\`\``);
    }
    
    if (discovery.graphContext) {
      parts.push(`\n## Graph Context\n${this.formatGraphContext(discovery.graphContext)}`);
    }
    
    return parts.join('\n\n');
  }
  
  private formatGraphContext(graph: GraphContext): string {
    // Format graph nodes and relationships for context
    const parts: string[] = [];
    
    parts.push(`**Entities**: ${graph.nodes.length}`);
    parts.push(`**Relationships**: ${graph.edges.length}`);
    
    // Group relationships by type
    const byType = new Map<string, number>();
    for (const edge of graph.edges) {
      byType.set(edge.type, (byType.get(edge.type) || 0) + 1);
    }
    
    parts.push('\n**Relationship Types**:');
    for (const [type, count] of byType.entries()) {
      parts.push(`- ${type}: ${count}`);
    }
    
    return parts.join('\n');
  }
}
```

### Phase 3: Planning Orchestrator

#### Responsibilities

1. **Plan Generation**
   - Create implementation plan grounded in discovered context
   - Reference specific files, functions, classes from KB results
   - Organize plan into logical phases/steps

2. **Todo List Creation**
   - Generate actionable todo items with file references
   - Order tasks by logical dependencies
   - Include acceptance criteria

3. **Validation**
   - Ensure plan references real codebase entities
   - Check for consistency with architecture patterns
   - Flag any remaining uncertainties

#### Implementation

```typescript
// agent-core/src/orchestration/planning-phase.ts

export interface Plan {
  title: string;
  summary: string;
  phases: PlanPhase[];
  todoList: TodoItem[];
  risks: string[];
  assumptions: string[];
  estimatedComplexity: "low" | "medium" | "high";
  references: CodeReference[];
}

export interface PlanPhase {
  name: string;
  description: string;
  steps: string[];
  affectedFiles: string[];
  estimatedTime: string;
}

export interface TodoItem {
  id: string;
  description: string;
  status: "pending" | "in_progress" | "completed";
  priority: number;
  dependencies: string[];
  fileReferences: string[];
}

export interface CodeReference {
  file: string;
  symbol?: string;
  lineRange?: [number, number];
  description: string;
}

export class PlanningOrchestrator {
  constructor(
    private claudeClient: ClaudeClient,
    private config: { maxTokens: number; temperature: number }
  ) {}
  
  async generate(params: {
    userQuery: string;
    discoveryContext: DiscoveryResult;
    synthesisInsights: SynthesisResult;
    conversationHistory: Message[];
  }): Promise<Plan> {
    const prompt = this.buildPlanningPrompt(params);
    
    const response = await this.claudeClient.complete({
      system: PLANNING_SYSTEM_PROMPT,
      messages: [
        ...params.conversationHistory,
        { role: "user", content: prompt }
      ],
      maxTokens: this.config.maxTokens,
      temperature: this.config.temperature
    });
    
    return this.parsePlan(response.content);
  }
  
  private buildPlanningPrompt(params: {
    userQuery: string;
    discoveryContext: DiscoveryResult;
    synthesisInsights: SynthesisResult;
  }): string {
    return `# Task: Create Implementation Plan

## User Request
${params.userQuery}

## Discovered Codebase Context
${this.formatDiscoveryForPlanning(params.discoveryContext)}

## Synthesis Insights
${this.formatSynthesisForPlanning(params.synthesisInsights)}

## Planning Instructions

Create a detailed, actionable implementation plan that:

1. **References Actual Code**: Use specific file paths, function names, and classes from the discovered context
2. **Follows Existing Patterns**: Align with architectural patterns and conventions found in the codebase
3. **Logical Phases**: Break down into clear phases with dependencies
4. **Actionable Todos**: Create concrete todo items that can be executed in Code mode
5. **Risk Awareness**: Call out risks identified in synthesis

**Output Format**: Structured markdown with clear sections and a todo checklist.

**Critical**: Ground all recommendations in the discovered codebase context. Don't suggest patterns or approaches that don't exist in the codebase.`;
  }
}
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1)

**Goal**: Set up core orchestration infrastructure

#### Tasks

1. **Create Orchestration Module**
   ```bash
   mkdir -p agent-core/src/orchestration
   touch agent-core/src/orchestration/types.ts
   touch agent-core/src/orchestration/architect-orchestrator.ts
   ```

2. **Implement Discovery Phase**
   - Create `DiscoveryOrchestrator` class
   - Implement query strategy generation
   - Add multi-query execution
   - Basic result aggregation

3. **Integration Point**
   - Modify `agent-core/src/main.ts` to detect architect mode
   - Route architect requests through new orchestrator
   - Maintain backward compatibility

4. **Testing**
   - Unit tests for query generation
   - Integration tests for KB multi-query
   - E2E test with sample architect request

**Deliverables:**
- ✅ Orchestration module structure
- ✅ Basic discovery phase working
- ✅ Integration with existing flow
- ✅ Passing tests (>80% coverage)

### Phase 2: Query Intelligence (Week 2)

**Goal**: Implement intelligent query generation and result validation

#### Tasks

1. **KB Query Planner**
   ```typescript
   // agent-core/src/kb/kb-query-planner.ts
   export class KBQueryPlanner {
     generateQueries(params: {
       userQuery: string;
       conversationHistory: Message[];
       maxQueries: number;
     }): DiscoveryQuery[]
   }
   ```

2. **Query Strategies**
   - Broad queries: High-level concepts
   - Specific queries: Exact matches
   - Pattern queries: Common patterns
   - Dependency queries: Related components

3. **Result Validation**
   ```typescript
   // agent-core/src/kb/kb-result-validator.ts
   export class KBResultValidator {
     validate(params: {
       chunks: EnrichedChunk[];
       userQuery: string;
       graphContext?: GraphContext;
     }): ValidationResult
   }
   ```

4. **Confidence Scoring**
   - Relevance scores from KB
   - Graph context correlation
   - Query-result alignment
   - Gap analysis

**Deliverables:**
- ✅ Intelligent query generation
- ✅ Multi-strategy search execution
- ✅ Result validation with confidence scoring
- ✅ Gap identification logic

### Phase 3: Synthesis & Planning (Week 3)

**Goal**: Complete synthesis and planning phases

#### Tasks

1. **Synthesis Orchestrator**
   - Context analysis
   - Assumption extraction
   - Question generation
   - Risk identification

2. **Planning Orchestrator**
   - Plan generation with KB grounding
   - Todo list creation
   - Code reference attribution
   - Markdown formatting

3. **Specialized Prompts**
   ```typescript
   // agent-core/src/llm/architect-prompts.ts
   export const DISCOVERY_PROMPT = `...`;
   export const SYNTHESIS_PROMPT = `...`;
   export const PLANNING_PROMPT = `...`;
   ```

4. **Streaming Support**
   - Stream discovery progress
   - Stream synthesis insights
   - Stream plan sections incrementally

**Deliverables:**
- ✅ Complete 3-phase workflow
- ✅ Specialized prompts for each phase
- ✅ Streaming for better UX
- ✅ Integration tests

### Phase 4: Polish & Optimization (Week 4)

**Goal**: Performance optimization and user experience improvements

#### Tasks

1. **Performance Optimization**
   - Parallel query execution
   - Result caching
   - Query deduplication
   - Timeout handling

2. **UI/UX Enhancements**
   - Progress indicators for each phase
   - Collapsible sections for detailed context
   - Inline code references with links
   - Mermaid diagrams for architecture

3. **Configuration**
   ```typescript
   // agent-core/src/orchestration/config.ts
   export interface ArchitectModeConfig {
     discovery: DiscoveryConfig;
     synthesis: SynthesisConfig;
     planning: PlanningConfig;
   }
   ```

4. **Documentation**
   - User guide for architect mode
   - Developer guide for orchestration
   - API reference
   - Example workflows

**Deliverables:**
- ✅ Optimized performance (<3s discovery)
- ✅ Enhanced UI with progress tracking
- ✅ Configuration options
- ✅ Complete documentation

---

## API Specifications

### Discovery Phase API

```typescript
interface DiscoveryRequest {
  userQuery: string;
  workspaceRoot: string;
  repoName: string;
  conversationHistory: Message[];
  config?: Partial<DiscoveryConfig>;
}

interface DiscoveryResponse {
  queries: DiscoveryQuery[];
  retrievedChunks: EnrichedChunk[];
  graphContext: GraphContext | null;
  confidence: number;
  gaps: string[];
  summary: string;
  executionTimeMs: number;
}

// Usage
const discovery = new DiscoveryOrchestrator(mcpClient, ...);
const result = await discovery.execute({
  userQuery: "Add authentication to the API",
  workspaceRoot: "/path/to/repo",
  repoName: "my-api",
  conversationHistory: []
});
```

### Events

```typescript
// Progress events during discovery
type DiscoveryEvent =
  | { type: "discovery_started"; totalQueries: number }
  | { type: "query_executed"; query: string; resultCount: number }
  | { type: "graph_context_loaded"; nodeCount: number; edgeCount: number }
  | { type: "discovery_completed"; result: DiscoveryResponse };

// Subscribe to events
discovery.on("event", (event: DiscoveryEvent) => {
  console.log(event);
});
```

---

## Testing Strategy

### Unit Tests

```typescript
// agent-core/tests/orchestration/discovery-phase.test.ts

describe("DiscoveryOrchestrator", () => {
  test("generates multiple strategic queries", async () => {
    const queries = await queryPlanner.generateQueries({
      userQuery: "Add user authentication",
      maxQueries: 5
    });
    
    expect(queries).toHaveLength(5);
    expect(queries[0].strategy).toBe("broad");
    expect(queries[1].strategy).toBe("specific");
  });
  
  test("deduplicates KB results by chunk_id", async () => {
    const results = [
      { hits: [{ chunk_id: "A" }, { chunk_id: "B" }] },
      { hits: [{ chunk_id: "B" }, { chunk_id: "C" }] }
    ];
    
    const aggregated = discovery.aggregateResults(results);
    
    expect(aggregated).toHaveLength(3);
    expect(aggregated.map(c => c.chunk_id)).toEqual(["A", "B", "C"]);
  });
  
  test("identifies gaps when no results found", async () => {
    const result = await discovery.execute({
      userQuery: "Add blockchain integration",
      repoName: "test-repo"
    });
    
    expect(result.gaps).toContain("No relevant code found in knowledge base");
  });
});
```

### Integration Tests

```typescript
// agent-core/tests/orchestration/architect-flow.test.ts

describe("Architect Mode E2E", () => {
  test("complete architect workflow", async () => {
    const orchestrator = new ArchitectOrchestrator(...);
    
    const result = await orchestrator.execute({
      userQuery: "Add rate limiting to REST API endpoints",
      workspaceRoot: "/test/repo",
      repoName: "test-api"
    });
    
    // Verify discovery phase
    expect(result.discovery.queries.length).toBeGreaterThan(0);
    expect(result.discovery.retrievedChunks.length).toBeGreaterThan(0);
    expect(result.discovery.confidence).toBeGreaterThan(0.5);
    
    // Verify synthesis phase
    expect(result.synthesis.assumptions.length).toBeGreaterThan(0);
    expect(result.synthesis.clarifyingQuestions.length).toBeGreaterThanOrEqual(0);
    
    // Verify planning phase
    expect(result.plan.phases.length).toBeGreaterThan(0);
    expect(result.plan.todoList.length).toBeGreaterThan(0);
    expect(result.plan.references.length).toBeGreaterThan(0);
  });
});
```

---

## Migration Plan

### Backward Compatibility

1. **Feature Flag**
   ```typescript
   const USE_ENHANCED_ARCHITECT = process.env.ARCHITECT_MODE_ENHANCED === "true";
   
   if (USE_ENHANCED_ARCHITECT && request.mode === "architect") {
     // New 3-phase orchestration
   } else {
     // Existing flow
   }
   ```

2. **Gradual Rollout**
   - Week 1: Internal testing with flag enabled
   - Week 2: Beta users opt-in
   - Week 3: Default on for new users
   - Week 4: Full rollout, remove legacy code

### User Communication

```markdown
# What's New in Architect Mode

Architect mode now includes **automatic codebase discovery**:

✨ **Smarter Context**: Automatically searches your codebase for relevant code
🎯 **Better Plans**: Grounded in your actual code patterns and architecture  
📚 **Comprehensive**: Multiple search strategies ensure nothing is missed
⚡ **Fast**: Complete discovery in <3 seconds

**What this means for you:**
- More accurate recommendations
- Fewer hallucinations or incorrect suggestions
- Plans that reference your actual code files
- Better understanding of existing patterns
```

---

## Success Metrics & KPIs

### Quantitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Discovery Execution Rate** | 100% | All architect requests trigger discovery |
| **Context Quality** | 80%+ | Plans reference actual codebase entities |
| **Hallucination Reduction** | 90% | Non-existent code recommendations decrease |
| **Discovery Latency** | <3s (p95) | Time from request to discovery complete |
| **Query Success Rate** | 85%+ | % of queries returning relevant results |
| **User Satisfaction** | 4.5/5 | Post-interaction survey |

### Qualitative Assessment

- **Plan Actionability**: Can plans be executed without clarification?
- **Code Reference Accuracy**: Do referenced files/functions exist?
- **Architecture Alignment**: Do plans follow existing patterns?
- **Gap Identification**: Are missing pieces correctly identified?

### Monitoring

```typescript
// Metrics to track
metrics.recordDiscoveryExecutionTime(durationMs);
metrics.recordQueryCount(queries.length);
metrics.recordContextQuality(confidence);
metrics.recordUserFeedback(rating, comments);
```

---

## Risk Mitigation

### Risk 1: Discovery Phase Timeout

**Impact**: High - Blocks entire workflow

**Mitigation**:
- Set aggressive timeout (5s default)
- Graceful degradation to basic search
- Cache frequently accessed context
- Parallel query execution

### Risk 2: Low Quality KB Results

**Impact**: Medium - Plan quality suffers

**Mitigation**:
- Confidence scoring with thresholds
- Fallback to broader queries
- Explicitly flag low-confidence plans
- Allow user to trigger re-discovery

### Risk 3: Over-Reliance on KB

**Impact**: Medium - Miss opportunities for innovation

**Mitigation**:
- Balance KB context with Claude's knowledge
- Encourage exploration of new patterns
- Synthesis phase identifies limitations
- Explicit "going beyond codebase" indicator

### Risk 4: Performance Regression

**Impact**: Medium - User experience degradation

**Mitigation**:
- Parallel query execution
- Result caching
- Progressive enhancement (show results as available)
- Performance budgets and monitoring

---

## Future Enhancements

### Phase 2 (Post-MVP)

1. **Adaptive Query Generation**
   - Learn from successful query patterns
   - User feedback on query quality
   - Fine-tune query strategies per project

2. **Cross-Repository Discovery**
   - Search across multiple related repos
   - Detect cross-repo dependencies
   - Unified context from mono-repo structure

3. **Historical Context**
   - Include git history in discovery
   - Understand evolution of patterns
   - Reference past decisions and changes

4. **Interactive Discovery**
   - User refines queries during discovery
   - Manual relevance scoring
   - Save custom query strategies

### Integration with EP-3 (Graph Intelligence)

```typescript
// Enhanced graph-aware discovery
const graphDiscovery = await discovery.executeWithGraph({
  userQuery: "Refactor authentication flow",
  graphQueries: [
    "impact_analysis:auth_middleware",
    "dependency_tree:user_service",
    "call_graph:login_endpoint"
  ]
});
```

**Benefits:**
- Impact analysis during discovery
- Dependency-aware context
- Architecture visualization
- Risk scoring based on graph centrality

---

## Appendix

### Example Discovery Output

```json
{
  "queries": [
    {
      "text": "FastAPI authentication middleware patterns",
      "strategy": "broad",
      "priority": 1
    },
    {
      "text": "JWT token validation implementation",
      "strategy": "specific",
      "priority": 2
    },
    {
      "text": "existing auth decorators or dependencies",
      "strategy": "pattern",
      "priority": 3
    }
  ],
  "retrievedChunks": [
    {
      "chunk_id": "...",
      "repo": "api-server",
      "path": "src/middleware/auth.py",
      "start_line": 10,
      "end_line": 45,
      "score": 0.92,
      "snippet": "def authenticate_request(...)..."
    }
  ],
  "confidence": 0.85,
  "gaps": [
    "No existing JWT library found - need to add dependency"
  ],
  "summary": "Found 12 relevant code chunks across 5 files. Graph context: 24 nodes, 18 relationships."
}
```

### Reference Implementation

See implementation in branch: `feature/ep11-architect-kb-discovery`

---

**Document End**