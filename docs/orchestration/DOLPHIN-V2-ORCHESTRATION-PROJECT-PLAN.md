# Dolphin v2 Orchestration Architecture - Project Plan

**Document Version:** 1.0  
**Date:** 2025-11-10  
**Status:** Planning - Ready for Implementation  
**Target:** Complete replacement of v1 Agent Core with research-backed orchestration

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Vision & Goals](#vision--goals)
3. [Architecture Overview](#architecture-overview)
4. [Core Components](#core-components)
5. [Implementation Phases](#implementation-phases)
6. [Technical Specifications](#technical-specifications)
7. [Testing Strategy](#testing-strategy)
8. [Integration Points](#integration-points)
9. [Risk Analysis](#risk-analysis)
10. [Success Criteria](#success-criteria)

---

## Executive Summary

### The Opportunity

Current research (2023-2025) demonstrates that **simple, well-executed architectures with strong planning workflows consistently outperform complex multi-agent systems**. The v2 orchestration architecture replaces Dolphin's Agent Core with a research-backed system that:

- Implements the proven **Research → Plan → Code → Validate** workflow
- Leverages Claude Code CLI as the execution engine (zero credential management)
- Uses multi-model orchestration (Opus for planning, Sonnet for coding, Haiku for exploration)
- Integrates deeply with Dolphin's existing semantic search capabilities
- Provides transparent, user-approved planning with iteration support

### Key Research Findings Applied

1. **Planning improves results by 40-50%** - Models that skip planning show dramatically worse performance
2. **Single-agent with adaptive workflows** - Proven to work well until clear limits (>20 tools, >50K context)
3. **Execution feedback loops** - Running code and feeding back errors is critical for quality
4. **2-3 self-correction iterations optimal** - Beyond this shows diminishing returns (deferred to future)
5. **Hybrid context management** - Tree-sitter repo maps + embeddings provide best results
6. **User transparency** - Showing plans builds trust and enables quick corrections

### Design Principles

1. **Simplicity First** - Start with single-agent, scale to multi-agent only when needed
2. **User Control** - Manual mode selection, explicit plan approval, optional verbose details
3. **Deep Integration** - Aggressively leverage existing Knowledge Bank capabilities
4. **Research-Driven** - Every architectural choice backed by scientific evidence
5. **Quality Over Speed** - Prioritize accuracy ($1/task acceptable)
6. **Observability Built-In** - Integrate with existing EP-1 observability infrastructure

---

## Vision & Goals

### Vision Statement

**Transform Dolphin into a state-of-the-art agentic coding assistant that rivals Claude Code and Aider through intelligent orchestration, transparent planning, and deep semantic code understanding.**

### Primary Goals

1. **Implement Research-Backed Workflow** - Research → Plan → Code → Validate with user approval gates
2. **Leverage Knowledge Bank** - Make semantic search a first-class citizen in the orchestration loop
3. **Enable Iterative Planning** - Support plan revision and refinement before execution
4. **Provide Transparency** - Users see and approve plans, understand token/cost implications
5. **Achieve Quality Targets** - Match or exceed Aider-level performance on coding tasks
6. **Maintain Flexibility** - Architecture supports future multi-agent expansion

### Non-Goals (Deferred)

- Self-correction loops (2-3 iterations) - Future enhancement
- Automatic complexity classification - Manual mode selection for v2
- Multi-agent orchestration - Architecture supports it, but start single-agent
- Automated evaluation framework - Built separately
- Budget caps and cost controls - Defer until usage patterns established
- Backward compatibility with v1 - Clean slate implementation

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     VSCode Extension (TypeScript)               │
│  • User Interface (Svelte 5 + shadcn-svelte)                   │
│  • Mode Selection UI (Editor vs Architect)                      │
│  • Plan Approval Flow                                           │
│  • Streaming Response Display                                   │
│  • Context Commands (@file, @folder, @selection)                │
└────────────────────────────┬────────────────────────────────────┘
                             │ JSON-RPC (stdio)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                Agent Core v2 (TypeScript/Bun)                   │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Orchestrator (Core State Machine)            │ │
│  │  • Mode routing (Editor vs Architect)                     │ │
│  │  • Workflow state management                              │ │
│  │  • Plan iteration tracking                                │ │
│  │  • User approval handling                                 │ │
│  └─────────────────────────┬─────────────────────────────────┘ │
│                            │                                   │
│  ┌─────────────────────────┴─────────────────────────────────┐ │
│  │              Workflow Implementations                      │ │
│  │                                                            │ │
│  │  ┌──────────────────┐       ┌──────────────────────────┐ │ │
│  │  │  Editor Workflow │       │  Architect Workflow      │ │ │
│  │  │  (Fast/Direct)   │       │  (Planning/Structured)   │ │ │
│  │  │                  │       │                          │ │ │
│  │  │  • Task input    │       │  1. Research Phase       │ │ │
│  │  │  • Execute       │       │     - KB search          │ │ │
│  │  │  • Response      │       │     - Codebase scan      │ │ │
│  │  └──────────────────┘       │  2. Planning Phase       │ │ │
│  │                             │     - Create plan.md     │ │ │
│  │                             │     - User approval      │ │ │
│  │                             │  3. Implementation       │ │ │
│  │                             │     - Execute plan       │ │ │
│  │                             │  4. Validation           │ │ │
│  │                             │     - Run tests          │ │ │
│  │                             └──────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                   │
│  ┌─────────────────────────┴─────────────────────────────────┐ │
│  │              Execution Layer                               │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────────────────────┐  │ │
│  │  │  ClaudeProvider (Multi-Model)                      │  │ │
│  │  │  • Opus 4 → Planning & Architecture                │  │ │
│  │  │  • Sonnet 4.5 → Coding & Implementation            │  │ │
│  │  │  • Haiku 4.5 → Exploration & Search                │  │ │
│  │  │  • CLI subprocess spawning (Kilocode pattern)      │  │ │
│  │  └────────────────────────────────────────────────────┘  │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────────────────────┐  │ │
│  │  │  PromptBuilder                                      │  │ │
│  │  │  • System prompts per phase                        │  │ │
│  │  │  • Context assembly                                │  │ │
│  │  │  • KB results integration                          │  │ │
│  │  │  • Tool call formatting                            │  │ │
│  │  └────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                   │
│  ┌─────────────────────────┴─────────────────────────────────┐ │
│  │              Context Management                            │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────────────────────┐  │ │
│  │  │  ContextBuilder                                     │  │ │
│  │  │  • Semantic search via KB                          │  │ │
│  │  │  • File gathering                                  │  │ │
│  │  │  • Symbol extraction                               │  │ │
│  │  │  • Context window tracking                         │  │ │
│  │  └────────────────────────────────────────────────────┘  │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────────────────────┐  │ │
│  │  │  RepoMapGenerator (Future)                         │  │ │
│  │  │  • Tree-sitter AST analysis                        │  │ │
│  │  │  • Aider-style repo maps                           │  │ │
│  │  │  • Symbol graphs                                   │  │ │
│  │  └────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                   │
│  ┌─────────────────────────┴─────────────────────────────────┐ │
│  │              State Management                              │ │
│  │                                                            │ │
│  │  ┌────────────────────────────────────────────────────┐  │ │
│  │  │  StateStore (TOML)                                  │  │ │
│  │  │  • Conversation persistence                        │  │ │
│  │  │  • Plan versioning                                 │  │ │
│  │  │  • Workflow state tracking                         │  │ │
│  │  └────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                             │ HTTP
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Knowledge Bank (Existing - Enhanced)               │
│  • Semantic search (hybrid BM25 + vector)                      │
│  • MMR diversity                                               │
│  • Cross-encoder reranking                                     │
│  • File content retrieval                                      │
│  • Symbol search (future enhancement)                          │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Observability (EP-1 Integration)                   │
│  • OpenTelemetry tracing                                       │
│  • Prometheus metrics                                          │
│  • Structured logging (JSONL)                                  │
│  • Grafana dashboards                                          │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow State Machine

```
                    ┌─────────────────┐
                    │   User Input    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Mode Selection  │
                    │ (User Choice)   │
                    └────┬───────┬────┘
                         │       │
        ┌────────────────┘       └────────────────┐
        │                                         │
        ▼                                         ▼
┌───────────────┐                        ┌────────────────┐
│ Editor Mode   │                        │ Architect Mode │
│ (Fast/Direct) │                        │ (Planning)     │
└───────┬───────┘                        └────────┬───────┘
        │                                         │
        │                                         ▼
        │                                ┌─────────────────┐
        │                                │ Research Phase  │
        │                                │ - KB Search     │
        │                                │ - File Scan     │
        │                                └────────┬────────┘
        │                                         │
        │                                         ▼
        │                                ┌─────────────────┐
        │                                │ Planning Phase  │
        │                                │ - Generate Plan │
        │                                └────────┬────────┘
        │                                         │
        │                                         ▼
        │                                ┌─────────────────┐
        │                                │ User Approval?  │
        │                                └────┬────┬───────┘
        │                                     │    │
        │                               Reject│    │Approve
        │                                     │    │
        │                     ┌───────────────┘    │
        │                     │                    │
        │                     ▼                    │
        │            ┌─────────────────┐          │
        │            │ Revise Plan?    │          │
        │            └────┬────┬───────┘          │
        │                 │    │                  │
        │           Revise│    │Cancel            │
        │                 │    │                  │
        │                 │    └──────────┐       │
        │                 │               │       │
        │                 └───────┐       │       │
        │                         │       │       │
        │                         ▼       │       │
        │               ┌──────────────┐  │       │
        │               │ Back to Plan │  │       │
        │               └──────────────┘  │       │
        │                         │       │       │
        │                         └───────┘       │
        │                                         │
        └─────────────────────┬───────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Execute Task     │
                    │ - Claude CLI     │
                    │ - Tool Calls     │
                    │ - KB Integration │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Stream Response  │
                    │ - Chunks         │
                    │ - Tool Results   │
                    │ - Artifacts      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Complete       │
                    └──────────────────┘
```

---

## Core Components

### 1. Orchestrator (Core State Machine)

**Purpose:** Central coordinator that manages workflow state, routes between modes, and handles user interactions.

**Responsibilities:**
- Accept user input and mode selection from VSCode extension
- Route to appropriate workflow implementation (Editor vs Architect)
- Track workflow state (idle, researching, planning, awaiting_approval, executing, complete)
- Handle plan approval/rejection/revision flow
- Coordinate with StateStore for persistence
- Emit telemetry to observability layer

**Key Interfaces:**
```typescript
interface Orchestrator {
  // Workflow management
  startTask(input: TaskInput): Promise<TaskSession>
  approveTask(sessionId: string): Promise<void>
  rejectTask(sessionId: string, feedback?: string): Promise<void>
  revisePlan(sessionId: string): Promise<void>
  cancelTask(sessionId: string): Promise<void>
  
  // State queries
  getSession(sessionId: string): Promise<TaskSession>
  getCurrentPhase(sessionId: string): Promise<WorkflowPhase>
  
  // Event streaming
  subscribeToUpdates(sessionId: string): AsyncIterator<WorkflowUpdate>
}

interface TaskInput {
  mode: 'editor' | 'architect'
  message: string
  context: ContextHints  // @file, @folder, @selection
  conversationHistory?: Message[]
}

interface TaskSession {
  id: string
  mode: 'editor' | 'architect'
  state: WorkflowState
  plan?: Plan
  execution?: ExecutionResult
  metadata: SessionMetadata
}

type WorkflowState = 
  | 'idle'
  | 'researching'
  | 'planning'
  | 'awaiting_approval'
  | 'plan_revision'
  | 'executing'
  | 'validating'
  | 'complete'
  | 'cancelled'
  | 'error'

interface WorkflowUpdate {
  type: 'state_change' | 'progress' | 'tool_call' | 'chunk' | 'error'
  sessionId: string
  timestamp: string
  data: unknown
}
```

**State Persistence:**
```toml
# .dolphin/sessions/{session-id}.toml

[session]
id = "sess_abc123"
mode = "architect"
state = "awaiting_approval"
created_at = "2025-11-10T10:00:00Z"
updated_at = "2025-11-10T10:05:00Z"

[input]
message = "Add authentication to the API endpoints"
context.files = ["kb/api/app.py"]

[plan]
version = 2
status = "pending_approval"
created_at = "2025-11-10T10:05:00Z"

[[plan.revisions]]
version = 1
created_at = "2025-11-10T10:02:00Z"
rejected_reason = "Missing error handling"
content = """
# Implementation Plan v1
[...]
"""

[[plan.revisions]]
version = 2
created_at = "2025-11-10T10:05:00Z"
content = """
# Implementation Plan v2 (Revised)
[...]
"""

[metadata]
model_used = "claude-opus-4-20250514"
tokens_used = 15234
estimated_cost = 0.45
```

---

### 2. Workflow Implementations

#### 2.1 Editor Workflow (Fast/Direct)

**Purpose:** Fast-path execution for simple, well-defined tasks that don't require planning.

**When to Use:**
- Single file edits
- Clear, specific instructions
- Quick fixes or refactors
- User explicitly selects "Editor Mode"

**Workflow Steps:**
```
1. Input → Accept task input
2. Context → Gather minimal context (current file, KB search if relevant)
3. Execute → Single Claude CLI call with Sonnet 4.5
4. Stream → Stream response back to user
5. Complete → Done
```

**Implementation:**
```typescript
class EditorWorkflow implements Workflow {
  async execute(input: TaskInput): AsyncIterator<WorkflowUpdate> {
    // 1. Build context
    const context = await this.contextBuilder.build({
      files: input.context.files,
      searchQuery: this.extractSearchIntent(input.message),
      maxTokens: 8000  // Smaller context for fast execution
    })
    
    // 2. Build prompt
    const prompt = this.promptBuilder.buildEditorPrompt({
      message: input.message,
      context,
      conversationHistory: input.conversationHistory
    })
    
    // 3. Execute with Sonnet (fast, capable model)
    const stream = await this.claudeProvider.execute({
      model: 'claude-sonnet-4-20250514',
      prompt,
      tools: this.getEditorTools(),  // File ops, KB search, bash
      thinkingMode: 'normal'  // No extended thinking for editor mode
    })
    
    // 4. Stream results
    for await (const chunk of stream) {
      yield { type: 'chunk', data: chunk }
    }
    
    yield { type: 'state_change', data: { state: 'complete' } }
  }
}
```

#### 2.2 Architect Workflow (Planning/Structured)

**Purpose:** Structured, multi-phase workflow for complex tasks requiring planning and user oversight.

**When to Use:**
- Multi-file changes
- Architectural modifications
- Unclear requirements needing exploration
- User explicitly selects "Architect Mode"

**Workflow Phases:**

**Phase 1: Research**
```
Goal: Understand the codebase and requirements
Model: Haiku 4.5 (fast, cost-effective for exploration)
Actions:
  • Semantic search via KB for relevant code
  • Read identified files
  • Explore directory structure
  • Understand dependencies and imports
Output: Research summary with key findings
```

**Phase 2: Planning**
```
Goal: Create detailed implementation plan
Model: Opus 4 (best reasoning for architecture)
Input: Research findings + original task
Actions:
  • Generate structured plan (plan.md)
  • Break down into steps
  • Identify files to modify/create
  • List dependencies and risks
  • Estimate complexity
Output: plan.md for user review
```

**Phase 3: User Approval**
```
Goal: Get user sign-off on plan
Actions:
  • Present plan in UI (concise view + verbose drilldown)
  • Show estimated cost/tokens
  • Await user action: Approve / Reject / Revise
Output: Approval decision
```

**Phase 4: Implementation**
```
Goal: Execute approved plan
Model: Sonnet 4.5 (balanced quality/cost for coding)
Input: Approved plan + full context
Actions:
  • Follow plan steps sequentially
  • Make code changes
  • Create/modify files
  • Run tests (if specified)
Output: Implementation results
```

**Phase 5: Validation**
```
Goal: Verify implementation (future enhancement)
Actions:
  • Run tests
  • Lint code
  • Check plan completion
Output: Validation report
```

**Implementation:**
```typescript
class ArchitectWorkflow implements Workflow {
  async execute(input: TaskInput): AsyncIterator<WorkflowUpdate> {
    const session = await this.createSession(input)
    
    try {
      // Phase 1: Research
      yield { type: 'state_change', data: { state: 'researching' } }
      const research = await this.researchPhase(input)
      yield { type: 'progress', data: { phase: 'research', result: research } }
      
      // Phase 2: Planning
      yield { type: 'state_change', data: { state: 'planning' } }
      const plan = await this.planningPhase(input, research)
      await this.stateStore.savePlan(session.id, plan)
      yield { type: 'progress', data: { phase: 'planning', plan } }
      
      // Phase 3: User Approval (blocking)
      yield { type: 'state_change', data: { state: 'awaiting_approval' } }
      const approved = await this.awaitApproval(session.id)
      
      if (!approved.approved) {
        if (approved.action === 'revise') {
          // Plan revision loop
          yield { type: 'state_change', data: { state: 'plan_revision' } }
          const revisedPlan = await this.revisePlan(plan, approved.feedback)
          await this.stateStore.savePlan(session.id, revisedPlan)
          yield { type: 'progress', data: { phase: 'planning', plan: revisedPlan } }
          // Back to approval
          yield { type: 'state_change', data: { state: 'awaiting_approval' } }
          // ... (handle revision loop)
        } else {
          yield { type: 'state_change', data: { state: 'cancelled' } }
          return
        }
      }
      
      // Phase 4: Implementation
      yield { type: 'state_change', data: { state: 'executing' } }
      const stream = await this.implementationPhase(plan)
      for await (const chunk of stream) {
        yield chunk
      }
      
      // Phase 5: Validation (future)
      // yield { type: 'state_change', data: { state: 'validating' } }
      // const validation = await this.validationPhase(...)
      
      yield { type: 'state_change', data: { state: 'complete' } }
      
    } catch (error) {
      yield { type: 'error', data: error }
      yield { type: 'state_change', data: { state: 'error' } }
    }
  }
  
  private async researchPhase(input: TaskInput): Promise<ResearchResult> {
    // 1. Semantic search for relevant code
    const kbResults = await this.kbClient.search({
      query: input.message,
      topK: 15,
      diversityThreshold: 0.7  // MMR for diversity
    })
    
    // 2. Build exploration context
    const context = await this.contextBuilder.build({
      kbResults,
      files: input.context.files,
      maxTokens: 20000  // Generous for research
    })
    
    // 3. Execute research with Haiku (fast explorer)
    const prompt = this.promptBuilder.buildResearchPrompt({
      task: input.message,
      context,
      systemPrompt: RESEARCH_SYSTEM_PROMPT
    })
    
    const response = await this.claudeProvider.execute({
      model: 'claude-haiku-4-20250514',
      prompt,
      tools: this.getResearchTools(),  // Read-only: KB search, read files, ls
      thinkingMode: 'normal'
    })
    
    return this.parseResearchResult(response)
  }
  
  private async planningPhase(
    input: TaskInput, 
    research: ResearchResult
  ): Promise<Plan> {
    // Build comprehensive context for planning
    const context = await this.contextBuilder.build({
      researchFindings: research,
      files: research.relevantFiles,
      maxTokens: 50000  // Large context for planning
    })
    
    // Execute planning with Opus (best reasoning)
    const prompt = this.promptBuilder.buildPlanningPrompt({
      task: input.message,
      research,
      context,
      systemPrompt: PLANNING_SYSTEM_PROMPT
    })
    
    const response = await this.claudeProvider.execute({
      model: 'claude-opus-4-20250514',
      prompt,
      tools: [],  // No tools during planning - just think
      thinkingMode: 'extended'  // Use extended thinking for complex planning
    })
    
    return this.parsePlan(response)
  }
  
  private async implementationPhase(plan: Plan): AsyncIterator<WorkflowUpdate> {
    const context = await this.contextBuilder.build({
      plan,
      files: plan.filesToModify,
      maxTokens: 80000  // Very large context for implementation
    })
    
    const prompt = this.promptBuilder.buildImplementationPrompt({
      plan,
      context,
      systemPrompt: IMPLEMENTATION_SYSTEM_PROMPT
    })
    
    const stream = await this.claudeProvider.execute({
      model: 'claude-sonnet-4-20250514',
      prompt,
      tools: this.getImplementationTools(),  // Full suite: edit, write, bash, KB
      thinkingMode: 'extended'  // Extended thinking for complex implementations
    })
    
    for await (const chunk of stream) {
      yield { type: 'chunk', data: chunk }
    }
  }
}
```

---

### 3. ClaudeProvider (Multi-Model Execution)

**Purpose:** Manages Claude CLI subprocess spawning with multi-model support and streaming response handling.

**Model Selection Strategy:**
```typescript
interface ModelConfig {
  research: 'claude-haiku-4-20250514'      // Fast, cost-effective
  planning: 'claude-opus-4-20250514'       // Best reasoning
  coding: 'claude-sonnet-4-20250514'       // Balanced
  editor: 'claude-sonnet-4-20250514'       // Fast enough, capable
}
```

**Implementation:**
```typescript
class ClaudeProvider {
  private cliPath: string
  
  constructor(config: ClaudeConfig) {
    this.cliPath = config.claudeCodePath || 'claude'
  }
  
  async execute(params: ExecutionParams): AsyncIterator<ClaudeChunk> {
    // Build CLI arguments
    const args = this.buildCliArgs(params)
    
    // Spawn subprocess
    const process = spawn(this.cliPath, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        // No ANTHROPIC_API_KEY - let CLI handle auth
      }
    })
    
    // Set up signal handlers
    const abortController = new AbortController()
    
    // Stream stdout
    const stream = this.parseClaudeStream(process.stdout)
    
    // Handle errors
    process.stderr.on('data', (chunk) => {
      this.logger.error('Claude CLI error', { chunk: chunk.toString() })
    })
    
    // Monitor process exit
    process.on('exit', (code) => {
      if (code !== 0) {
        this.logger.error('Claude CLI exited with error', { code })
      }
    })
    
    return stream
  }
  
  private buildCliArgs(params: ExecutionParams): string[] {
    const args = [
      '-p',  // Non-interactive mode
      '--model', params.model,
    ]
    
    // Add thinking mode if extended
    if (params.thinkingMode === 'extended') {
      // Note: Research how to pass extended thinking to CLI
      // May need to include in prompt with "think hard" keyword
    }
    
    // Build prompt with system instructions + tools
    const fullPrompt = this.buildFullPrompt(params)
    args.push(fullPrompt)
    
    return args
  }
  
  private async *parseClaudeStream(
    stdout: ReadableStream
  ): AsyncIterator<ClaudeChunk> {
    // Parse streaming JSON or text chunks from Claude CLI
    // Handle different message types:
    // - Text chunks
    // - Tool use requests
    // - Tool use results
    // - Thinking blocks
    // - Error messages
    
    const reader = stdout.getReader()
    let buffer = ''
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      
      buffer += new TextDecoder().decode(value)
      
      // Parse complete chunks (may be JSON or markdown)
      const chunks = this.extractChunks(buffer)
      for (const chunk of chunks) {
        yield this.parseChunk(chunk)
      }
    }
  }
  
  private buildFullPrompt(params: ExecutionParams): string {
    // Combine system prompt + context + tools + user message
    let prompt = ''
    
    // System instructions
    if (params.systemPrompt) {
      prompt += `${params.systemPrompt}\n\n`
    }
    
    // Context
    if (params.context) {
      prompt += this.formatContext(params.context)
      prompt += '\n\n'
    }
    
    // Tools (if any)
    if (params.tools && params.tools.length > 0) {
      prompt += this.formatTools(params.tools)
      prompt += '\n\n'
    }
    
    // User message
    prompt += params.prompt
    
    return prompt
  }
  
  private formatContext(context: Context): string {
    let formatted = '# Context\n\n'
    
    if (context.kbResults) {
      formatted += '## Knowledge Bank Search Results\n\n'
      for (const result of context.kbResults) {
        formatted += `### ${result.file}:${result.startLine}-${result.endLine}\n`
        formatted += '```' + result.language + '\n'
        formatted += result.content + '\n'
        formatted += '```\n\n'
      }
    }
    
    if (context.files) {
      formatted += '## Current Files\n\n'
      for (const file of context.files) {
        formatted += `### ${file.path}\n`
        formatted += '```' + file.language + '\n'
        formatted += file.content + '\n'
        formatted += '```\n\n'
      }
    }
    
    return formatted
  }
  
  private formatTools(tools: Tool[]): string {
    let formatted = '# Available Tools\n\n'
    formatted += 'You have access to the following tools:\n\n'
    
    for (const tool of tools) {
      formatted += `## ${tool.name}\n`
      formatted += `${tool.description}\n\n`
      if (tool.parameters) {
        formatted += 'Parameters:\n'
        formatted += JSON.stringify(tool.parameters, null, 2)
        formatted += '\n\n'
      }
    }
    
    return formatted
  }
}
```

**Authentication Handling:**
```typescript
class AuthManager {
  async detectAuthStatus(): Promise<AuthStatus> {
    const settingsPath = join(homedir(), '.claude', 'settings.json')
    const hasOAuth = existsSync(settingsPath)
    const hasApiKey = Boolean(process.env.ANTHROPIC_API_KEY)
    
    if (hasOAuth && !hasApiKey) {
      return {
        authenticated: true,
        method: 'subscription',
        source: 'Claude CLI OAuth'
      }
    }
    
    if (!hasOAuth && hasApiKey) {
      return {
        authenticated: true,
        method: 'api_key',
        source: 'ANTHROPIC_API_KEY',
        warning: 'Using pay-as-you-go billing'
      }
    }
    
    if (hasOAuth && hasApiKey) {
      return {
        authenticated: true,
        method: 'subscription',
        warning: 'ANTHROPIC_API_KEY ignored, using OAuth'
      }
    }
    
    return {
      authenticated: false,
      method: 'none',
      error: 'No authentication configured'
    }
  }
  
  async ensureAuthenticated(): Promise<void> {
    const status = await this.detectAuthStatus()
    
    if (!status.authenticated) {
      throw new Error(
        'Claude CLI not authenticated. Run: claude (and select authentication method)'
      )
    }
    
    if (status.warning) {
      this.logger.warn('Auth warning', { warning: status.warning })
    }
  }
}
```

---

### 4. ContextBuilder (KB Integration)

**Purpose:** Assembles relevant context from multiple sources, with Knowledge Bank as primary source.

**Context Sources:**
1. Knowledge Bank semantic search (primary)
2. Explicitly mentioned files (@file)
3. Current workspace/folder context
4. Conversation history
5. Repo map (future)

**Implementation:**
```typescript
class ContextBuilder {
  constructor(
    private kbClient: KBClient,
    private fileSystem: FileSystem,
    private repoMapGenerator?: RepoMapGenerator  // Future
  ) {}
  
  async build(params: ContextBuildParams): Promise<Context> {
    const context: Context = {
      kbResults: [],
      files: [],
      repoMap: null,
      totalTokens: 0,
      truncated: false
    }
    
    // 1. Semantic search via KB (if query provided)
    if (params.searchQuery) {
      context.kbResults = await this.searchKnowledgeBank(params.searchQuery)
      context.totalTokens += this.estimateTokens(context.kbResults)
    }
    
    // 2. Explicitly requested files
    if (params.files && params.files.length > 0) {
      context.files = await this.loadFiles(params.files)
      context.totalTokens += this.estimateTokens(context.files)
    }
    
    // 3. Repo map (if enabled)
    if (this.repoMapGenerator && params.includeRepoMap) {
      context.repoMap = await this.repoMapGenerator.generate(params.scope)
      context.totalTokens += this.estimateTokens(context.repoMap)
    }
    
    // 4. Apply token limit
    if (context.totalTokens > params.maxTokens) {
      context = await this.truncateContext(context, params.maxTokens)
      context.truncated = true
    }
    
    return context
  }
  
  private async searchKnowledgeBank(query: string): Promise<KBResult[]> {
    try {
      const results = await this.kbClient.search({
        query,
        topK: 20,  // Request more, filter later
        diversityThreshold: 0.7,  // MMR for diversity
        useReranking: true  // Cross-encoder reranking
      })
      
      // Transform KB results to Context format
      return results.map(r => ({
        file: r.file_path,
        startLine: r.start_line,
        endLine: r.end_line,
        content: r.snippet_text,
        language: r.language,
        score: r.score,
        chunkId: r.chunk_id
      }))
    } catch (error) {
      this.logger.error('KB search failed', { error, query })
      return []
    }
  }
  
  private async loadFiles(filePaths: string[]): Promise<FileContent[]> {
    const files = await Promise.all(
      filePaths.map(async (path) => {
        const content = await this.fileSystem.readFile(path)
        const language = this.detectLanguage(path)
        return {
          path,
          content,
          language,
          tokens: this.estimateFileTokens(content)
        }
      })
    )
    return files
  }
  
  private async truncateContext(
    context: Context,
    maxTokens: number
  ): Promise<Context> {
    // Strategy: Prioritize explicitly requested files > KB results > repo map
    let remaining = maxTokens
    const truncated = { ...context }
    
    // 1. Keep all explicitly requested files (high priority)
    const fileTokens = this.estimateTokens(truncated.files)
    remaining -= fileTokens
    
    // 2. Trim KB results if needed
    if (remaining < 0) {
      // Need to cut files - take top N by importance
      const filesWithPriority = this.prioritizeFiles(truncated.files)
      truncated.files = this.fitFilesInBudget(filesWithPriority, maxTokens * 0.7)
      remaining = maxTokens - this.estimateTokens(truncated.files)
    }
    
    // 3. Add KB results up to remaining budget
    const kbResultsInBudget = this.fitKBResultsInBudget(
      truncated.kbResults,
      remaining
    )
    truncated.kbResults = kbResultsInBudget
    
    // 4. Drop repo map if out of budget (lowest priority)
    const totalUsed = this.estimateTokens(truncated)
    if (totalUsed > maxTokens) {
      truncated.repoMap = null
    }
    
    return truncated
  }
  
  private fitKBResultsInBudget(
    results: KBResult[],
    tokenBudget: number
  ): KBResult[] {
    // Sort by score (best results first)
    const sorted = [...results].sort((a, b) => b.score - a.score)
    
    const fitted: KBResult[] = []
    let used = 0
    
    for (const result of sorted) {
      const tokens = this.estimateResultTokens(result)
      if (used + tokens <= tokenBudget) {
        fitted.push(result)
        used += tokens
      } else {
        break
      }
    }
    
    return fitted
  }
}
```

**Knowledge Bank Prompt Integration:**

For planning and research phases, explicitly guide Claude to use KB:

```typescript
const RESEARCH_SYSTEM_PROMPT = `
You are Claude, an AI assistant helping with code research and exploration.

Your task is to thoroughly research the codebase to understand how to complete the user's request.

# Knowledge Bank Integration

You have access to a semantic code search via the search_knowledge tool. This searches a vector database of the entire codebase.

**When to search:**
- At the start of your research to find relevant code
- When you need to understand how something is implemented
- When looking for examples or patterns
- When trying to locate specific functions, classes, or APIs

**Search strategy:**
1. Start with a broad search to understand the codebase structure
2. Follow up with specific searches for implementations you need to modify
3. Use the results to guide which files to read in detail

**Example searches:**
- "authentication and login handlers"
- "database connection setup"
- "API endpoint definitions"
- "error handling middleware"

# Research Output

Provide a structured research summary with:
1. Key findings (what you learned)
2. Relevant files and their purposes
3. Dependencies and relationships
4. Areas of complexity or risk
5. Questions or clarifications needed
`

const PLANNING_SYSTEM_PROMPT = `
You are Claude, an expert software architect creating implementation plans.

# Context

You've completed research on the codebase. Now create a detailed implementation plan.

# Plan Structure

Your plan should include:

1. **Overview** - High-level approach
2. **Files to Modify** - List with specific changes
3. **Files to Create** - New files needed
4. **Implementation Steps** - Ordered sequence
5. **Dependencies** - External or internal
6. **Testing Strategy** - How to validate
7. **Risks & Considerations** - Potential issues
8. **Estimated Complexity** - Low/Medium/High

# Format

Use markdown with clear sections. Be specific about:
- Exact file paths
- Function/class names to modify
- Code patterns to follow
- Error handling requirements

The user will review this plan before you implement it, so be thorough and clear.
`
```

---

### 5. PromptBuilder (System Prompts)

**Purpose:** Constructs phase-specific prompts with appropriate system instructions, context, and tool descriptions.

**Prompt Templates:**

```typescript
class PromptBuilder {
  buildResearchPrompt(params: ResearchPromptParams): string {
    return `
${RESEARCH_SYSTEM_PROMPT}

# Task

${params.task}

# Initial Context

${this.formatContext(params.context)}

# Instructions

1. Start by searching the Knowledge Bank to find relevant code
2. Read the most relevant files identified
3. Explore the codebase structure
4. Document your findings clearly

Begin your research now.
`
  }
  
  buildPlanningPrompt(params: PlanningPromptParams): string {
    return `
${PLANNING_SYSTEM_PROMPT}

# Task

${params.task}

# Research Findings

${this.formatResearch(params.research)}

# Context

${this.formatContext(params.context)}

# Instructions

Create a detailed implementation plan following the structure outlined in your system prompt.

Remember: The user will review this plan, so be thorough and specific.

Begin creating the plan now.
`
  }
  
  buildImplementationPrompt(params: ImplementationPromptParams): string {
    return `
You are Claude, an expert software engineer implementing an approved plan.

# Approved Plan

${this.formatPlan(params.plan)}

# Context

${this.formatContext(params.context)}

# Instructions

Implement the plan step by step:

1. Follow the plan's sequence
2. Make precise edits using the available tools
3. Explain your changes as you make them
4. Run tests if specified in the plan
5. Verify each step before moving to the next

If you encounter issues:
- Explain the problem clearly
- Suggest solutions
- Ask for guidance if needed

Begin implementation now.
`
  }
  
  buildEditorPrompt(params: EditorPromptParams): string {
    return `
You are Claude, an expert coding assistant helping with a specific task.

# Task

${params.message}

# Context

${this.formatContext(params.context)}

# Instructions

Complete the requested task directly and efficiently. Use the available tools to:
- Search the codebase if needed (search_knowledge)
- Read or modify files
- Execute commands

Be concise but thorough. Make the necessary changes and explain what you did.

Begin now.
`
  }
}
```

---

### 6. StateStore (TOML Persistence)

**Purpose:** Persists conversation state, plans, and workflow history in human-readable TOML format.

**Storage Structure:**
```
.dolphin/
├── config.toml                    # Global configuration
├── sessions/                      # Active sessions
│   ├── sess_abc123.toml          # Session state
│   ├── sess_def456.toml
│   └── ...
├── plans/                         # Plan archives
│   ├── plan_abc123_v1.md
│   ├── plan_abc123_v2.md
│   └── ...
└── conversations/                 # Conversation history
    ├── conv_abc123.toml
    └── ...
```

**Session TOML Schema:**
```toml
[session]
id = "sess_abc123"
conversation_id = "conv_abc123"
mode = "architect"  # or "editor"
state = "awaiting_approval"
created_at = "2025-11-10T10:00:00Z"
updated_at = "2025-11-10T10:05:00Z"

[input]
message = "Add authentication to the API endpoints"
context.files = ["kb/api/app.py", "kb/api/auth.py"]
context.folders = []
context.selection = ""

[research]
completed_at = "2025-11-10T10:02:00Z"
model = "claude-haiku-4-20250514"
tokens_used = 3421
findings = """
Key findings from research phase:
- Current API uses no authentication
- FastAPI supports OAuth2 with bearer tokens
- Existing models in kb/api/models.py
[...]
"""

[[research.kb_searches]]
query = "authentication API"
results_count = 8
top_result = "kb/api/middleware.py"

[[research.kb_searches]]
query = "FastAPI OAuth2"
results_count = 5
top_result = "kb/api/deps.py"

[plan]
version = 2
status = "pending_approval"  # or "approved", "rejected", "cancelled"
created_at = "2025-11-10T10:05:00Z"
approved_at = ""
model = "claude-opus-4-20250514"
tokens_used = 8934
estimated_cost = 0.34
content_path = "plans/plan_abc123_v2.md"

[[plan.revisions]]
version = 1
created_at = "2025-11-10T10:02:00Z"
rejected_at = "2025-11-10T10:03:00Z"
rejected_reason = "Missing error handling and security considerations"
content_path = "plans/plan_abc123_v1.md"

[[plan.revisions]]
version = 2
created_at = "2025-11-10T10:05:00Z"
content_path = "plans/plan_abc123_v2.md"

[execution]
started_at = ""
completed_at = ""
model = "claude-sonnet-4-20250514"
tokens_used = 0
cost = 0.0

[[execution.steps]]
step_number = 1
description = "Create authentication middleware"
status = "pending"
started_at = ""
completed_at = ""

[metadata]
total_tokens = 12355
total_cost = 0.34
models_used = ["claude-haiku-4-20250514", "claude-opus-4-20250514"]
```

**Implementation:**
```typescript
class StateStore {
  private storagePath: string
  
  constructor(config: StateStoreConfig) {
    this.storagePath = config.storagePath || '.dolphin'
    this.ensureDirectories()
  }
  
  async saveSession(session: TaskSession): Promise<void> {
    const sessionPath = join(this.storagePath, 'sessions', `${session.id}.toml`)
    const toml = this.serializeSession(session)
    await writeFile(sessionPath, toml, 'utf-8')
  }
  
  async loadSession(sessionId: string): Promise<TaskSession | null> {
    const sessionPath = join(this.storagePath, 'sessions', `${sessionId}.toml`)
    
    if (!existsSync(sessionPath)) {
      return null
    }
    
    const toml = await readFile(sessionPath, 'utf-8')
    return this.deserializeSession(toml)
  }
  
  async savePlan(sessionId: string, plan: Plan): Promise<void> {
    // Save plan content as markdown
    const planPath = join(
      this.storagePath,
      'plans',
      `plan_${sessionId}_v${plan.version}.md`
    )
    await writeFile(planPath, plan.content, 'utf-8')
    
    // Update session with plan metadata
    const session = await this.loadSession(sessionId)
    if (session) {
      session.plan = {
        ...plan,
        contentPath: planPath
      }
      await this.saveSession(session)
    }
  }
  
  async loadPlan(sessionId: string, version?: number): Promise<Plan | null> {
    const session = await this.loadSession(sessionId)
    if (!session?.plan) return null
    
    const planVersion = version || session.plan.version
    const planPath = join(
      this.storagePath,
      'plans',
      `plan_${sessionId}_v${planVersion}.md`
    )
    
    if (!existsSync(planPath)) return null
    
    const content = await readFile(planPath, 'utf-8')
    return {
      ...session.plan,
      content
    }
  }
  
  async listSessions(): Promise<SessionSummary[]> {
    const sessionsDir = join(this.storagePath, 'sessions')
    const files = await readdir(sessionsDir)
    
    const summaries = await Promise.all(
      files
        .filter(f => f.endsWith('.toml'))
        .map(async f => {
          const session = await this.loadSession(f.replace('.toml', ''))
          return this.toSummary(session)
        })
    )
    
    return summaries.sort((a, b) => 
      b.updatedAt.getTime() - a.updatedAt.getTime()
    )
  }
  
  async deleteSession(sessionId: string): Promise<void> {
    const sessionPath = join(this.storagePath, 'sessions', `${sessionId}.toml`)
    await unlink(sessionPath)
    
    // Also delete associated plans
    const plansDir = join(this.storagePath, 'plans')
    const planFiles = await readdir(plansDir)
    const sessionPlans = planFiles.filter(f => f.startsWith(`plan_${sessionId}_`))
    
    await Promise.all(
      sessionPlans.map(f => unlink(join(plansDir, f)))
    )
  }
  
  private serializeSession(session: TaskSession): string {
    // Convert TaskSession to TOML format
    return TOML.stringify(this.sessionToTOMLObject(session))
  }
  
  private deserializeSession(toml: string): TaskSession {
    const obj = TOML.parse(toml)
    return this.tomlObjectToSession(obj)
  }
}
```

---

### 7. VSCode Extension Integration

**UI Components for v2:**

**Mode Selection UI:**
```typescript
// In webview (Svelte)
<script lang="ts">
  let selectedMode: 'editor' | 'architect' = 'editor'
  let showModeTooltip = false
</script>

<div class="mode-selector">
  <button
    class="mode-button"
    class:active={selectedMode === 'editor'}
    on:click={() => selectedMode = 'editor'}
  >
    <Icon name="zap" />
    <span>Editor Mode</span>
    <Tooltip>
      Fast, direct execution for simple tasks
    </Tooltip>
  </button>
  
  <button
    class="mode-button"
    class:active={selectedMode === 'architect'}
    on:click={() => selectedMode = 'architect'}
  >
    <Icon name="blueprint" />
    <span>Architect Mode</span>
    <Tooltip>
      Structured planning for complex changes
    </Tooltip>
  </button>
</div>
```

**Plan Approval UI:**
```typescript
<script lang="ts">
  export let plan: Plan
  export let onApprove: () => void
  export let onReject: () => void
  export let onRevise: (feedback: string) => void
  
  let showVerbose = false
  let revisionFeedback = ''
  let showRevisionDialog = false
</script>

<div class="plan-approval">
  <div class="plan-header">
    <h3>Implementation Plan (v{plan.version})</h3>
    <Badge>Awaiting Your Approval</Badge>
  </div>
  
  <!-- Concise view -->
  <div class="plan-summary">
    <h4>Overview</h4>
    <p>{plan.overview}</p>
    
    <h4>Files to Modify ({plan.filesToModify.length})</h4>
    <ul>
      {#each plan.filesToModify.slice(0, 5) as file}
        <li><code>{file}</code></li>
      {/each}
      {#if plan.filesToModify.length > 5}
        <li>... and {plan.filesToModify.length - 5} more</li>
      {/if}
    </ul>
    
    <h4>Estimated Complexity</h4>
    <Badge variant={plan.complexity}>{plan.complexity}</Badge>
    
    <button on:click={() => showVerbose = !showVerbose}>
      {showVerbose ? 'Hide' : 'Show'} Full Plan
    </button>
  </div>
  
  <!-- Verbose view (expandable) -->
  {#if showVerbose}
    <div class="plan-verbose">
      <Markdown content={plan.content} />
    </div>
  {/if}
  
  <!-- Cost estimate -->
  <div class="cost-estimate">
    <Icon name="dollar-sign" />
    <span>Estimated cost: ${plan.estimatedCost.toFixed(2)}</span>
    <span class="tokens">~{plan.estimatedTokens.toLocaleString()} tokens</span>
  </div>
  
  <!-- Action buttons -->
  <div class="plan-actions">
    <button class="approve" on:click={onApprove}>
      <Icon name="check" />
      Approve & Execute
    </button>
    
    <button class="revise" on:click={() => showRevisionDialog = true}>
      <Icon name="edit" />
      Request Revision
    </button>
    
    <button class="reject" on:click={onReject}>
      <Icon name="x" />
      Cancel
    </button>
  </div>
</div>

{#if showRevisionDialog}
  <Dialog on:close={() => showRevisionDialog = false}>
    <h3>Request Plan Revision</h3>
    <p>What changes would you like Claude to make to the plan?</p>
    
    <textarea
      bind:value={revisionFeedback}
      placeholder="Example: Add error handling for database failures"
      rows="4"
    />
    
    <div class="dialog-actions">
      <button on:click={() => {
        onRevise(revisionFeedback)
        showRevisionDialog = false
      }}>
        Request Revision
      </button>
      <button on:click={() => showRevisionDialog = false}>
        Cancel
      </button>
    </div>
  </Dialog>
{/if}
```

**Progress Tracking UI:**
```typescript
<script lang="ts">
  export let session: TaskSession
  
  $: progress = calculateProgress(session)
</script>

<div class="workflow-progress">
  <div class="phase-indicator">
    <div class="phase" class:active={session.state === 'researching'}>
      <Icon name="search" />
      <span>Research</span>
    </div>
    
    <div class="phase" class:active={session.state === 'planning'}>
      <Icon name="file-text" />
      <span>Planning</span>
    </div>
    
    <div class="phase" class:active={session.state === 'awaiting_approval'}>
      <Icon name="hand" />
      <span>Approval</span>
    </div>
    
    <div class="phase" class:active={session.state === 'executing'}>
      <Icon name="code" />
      <span>Implementing</span>
    </div>
    
    <div class="phase" class:active={session.state === 'complete'}>
      <Icon name="check-circle" />
      <span>Complete</span>
    </div>
  </div>
  
  <div class="progress-bar">
    <div class="progress-fill" style="width: {progress}%"></div>
  </div>
</div>
```

**Extension Message Handlers:**
```typescript
// extension.ts
class DolphinExtensionV2 {
  private agentCore: ChildProcess
  private messageHandler: MessageHandler
  
  async activate(context: vscode.ExtensionContext) {
    // Start Agent Core v2
    this.agentCore = spawn('bun', ['run', 'agent-core/src/main.ts'], {
      stdio: ['pipe', 'pipe', 'pipe']
    })
    
    // Set up message handler
    this.messageHandler = new MessageHandler(
      this.agentCore.stdin,
      this.agentCore.stdout
    )
    
    // Register commands
    context.subscriptions.push(
      vscode.commands.registerCommand('dolphin.startTask', this.startTask),
      vscode.commands.registerCommand('dolphin.approvePlan', this.approvePlan),
      vscode.commands.registerCommand('dolphin.rejectPlan', this.rejectPlan),
      vscode.commands.registerCommand('dolphin.revisePlan', this.revisePlan)
    )
    
    // Set up webview
    this.setupWebview(context)
  }
  
  private async startTask(params: {
    mode: 'editor' | 'architect',
    message: string,
    context: ContextHints
  }) {
    const response = await this.messageHandler.request({
      jsonrpc: '2.0',
      id: generateId(),
      method: 'task.start',
      params
    })
    
    return response.result
  }
  
  private async approvePlan(sessionId: string) {
    await this.messageHandler.request({
      jsonrpc: '2.0',
      id: generateId(),
      method: 'task.approve',
      params: { sessionId }
    })
  }
  
  private async rejectPlan(sessionId: string) {
    await this.messageHandler.request({
      jsonrpc: '2.0',
      id: generateId(),
      method: 'task.reject',
      params: { sessionId }
    })
  }
  
  private async revisePlan(sessionId: string, feedback: string) {
    await this.messageHandler.request({
      jsonrpc: '2.0',
      id: generateId(),
      method: 'task.revise',
      params: { sessionId, feedback }
    })
  }
}
```

---

## Implementation Phases

### Phase 1: Foundation (Weeks 1-3)

**Goal:** Build core orchestration infrastructure and single-path execution.

#### Week 1: Core Architecture
- **Days 1-2:** Project setup and architecture scaffolding
  - Create new agent-core-v2 directory structure
  - Set up TypeScript/Bun configuration
  - Define core interfaces and types
  - Set up logging infrastructure
  
- **Days 3-5:** Orchestrator implementation
  - Implement Orchestrator class with state machine
  - JSON-RPC message handlers
  - StateStore with TOML persistence
  - Basic workflow routing
  
- **Deliverables:**
  - ✅ Orchestrator class with state machine
  - ✅ StateStore with TOML read/write
  - ✅ JSON-RPC communication layer
  - ✅ Basic test suite (50+ tests)

#### Week 2: Claude Provider & Workflows
- **Days 1-3:** ClaudeProvider implementation
  - CLI subprocess spawning
  - Multi-model support (Opus, Sonnet, Haiku)
  - Stream parsing and chunk handling
  - Authentication detection and management
  
- **Days 4-5:** Editor Workflow (simple path)
  - Implement EditorWorkflow class
  - Basic prompt building
  - Context assembly
  - End-to-end test
  
- **Deliverables:**
  - ✅ ClaudeProvider with multi-model support
  - ✅ EditorWorkflow working end-to-end
  - ✅ Authentication handling
  - ✅ Stream response parsing
  - ✅ 30+ additional tests

#### Week 3: Context Management & KB Integration
- **Days 1-3:** ContextBuilder implementation
  - KB client integration
  - File system operations
  - Context assembly and token tracking
  - Truncation strategies
  
- **Days 4-5:** Integration and testing
  - Connect Editor Workflow with full context
  - Knowledge Bank search integration
  - End-to-end testing with real KB
  - Performance profiling
  
- **Deliverables:**
  - ✅ ContextBuilder with KB integration
  - ✅ Token management and truncation
  - ✅ Editor Mode working end-to-end with KB
  - ✅ Integration tests
  - ✅ Performance baseline established

**Phase 1 Success Criteria:**
- [ ] Editor Mode can handle simple tasks end-to-end
- [ ] Claude CLI subprocess spawning works reliably
- [ ] KB search integration functional
- [ ] State persists in TOML correctly
- [ ] 100+ tests passing
- [ ] Authentication detection works
- [ ] Streaming responses display in extension

---

### Phase 2: Architect Workflow (Weeks 4-6)

**Goal:** Implement full planning workflow with approval gates.

#### Week 4: Research & Planning Phases
- **Days 1-2:** Research phase implementation
  - Implement ResearchPhase with Haiku
  - KB search prompting
  - Research summary generation
  - State persistence
  
- **Days 3-5:** Planning phase implementation
  - Implement PlanningPhase with Opus
  - Plan generation with structured output
  - Plan versioning and storage
  - Plan parsing and validation
  
- **Deliverables:**
  - ✅ ResearchPhase working with Haiku
  - ✅ PlanningPhase working with Opus
  - ✅ Plan.md generation and parsing
  - ✅ Plan versioning in StateStore
  - ✅ 40+ additional tests

#### Week 5: User Approval Flow
- **Days 1-3:** Approval handling in Agent Core
  - Implement approval state management
  - Plan revision logic
  - Feedback incorporation
  - Approval timeout handling
  
- **Days 4-5:** VSCode UI integration
  - Plan display UI (Svelte components)
  - Approval/rejection buttons
  - Revision feedback dialog
  - Progress indicators
  
- **Deliverables:**
  - ✅ Approval state machine working
  - ✅ Plan revision loop functional
  - ✅ UI components for plan approval
  - ✅ User feedback integration
  - ✅ 30+ additional tests

#### Week 6: Implementation & Validation
- **Days 1-3:** Implementation phase
  - Implement ImplementationPhase with Sonnet
  - Step-by-step execution
  - Progress tracking
  - Error handling
  
- **Days 4-5:** End-to-end testing and refinement
  - Full Architect workflow testing
  - Real-world task validation
  - Performance optimization
  - Bug fixes and polish
  
- **Deliverables:**
  - ✅ ImplementationPhase working with Sonnet
  - ✅ Full Architect workflow end-to-end
  - ✅ UI shows all phases correctly
  - ✅ Error handling and recovery
  - ✅ 40+ additional tests

**Phase 2 Success Criteria:**
- [ ] Architect Mode completes complex tasks end-to-end
- [ ] Plan approval flow works smoothly
- [ ] Plan revision works correctly
- [ ] Multi-model orchestration functional
- [ ] UI shows all workflow phases
- [ ] 200+ tests passing
- [ ] Cost tracking accurate

---

### Phase 3: Polish & Optimization (Weeks 7-9)

**Goal:** Refine UX, optimize performance, comprehensive testing.

#### Week 7: UX Refinement
- **Days 1-2:** Mode selection UX
  - Improve mode selector UI
  - Add mode descriptions and tooltips
  - Smart mode suggestions (future)
  - User preference persistence
  
- **Days 3-5:** Plan display enhancements
  - Concise view optimization
  - Verbose drilldown improvements
  - Cost/token estimates
  - Plan comparison (across versions)
  
- **Deliverables:**
  - ✅ Polished mode selection UI
  - ✅ Enhanced plan display
  - ✅ Cost estimates visible
  - ✅ Plan version comparison
  - ✅ User preference handling

#### Week 8: Observability Integration
- **Days 1-3:** EP-1 integration
  - Add OpenTelemetry spans for workflows
  - Emit Prometheus metrics
  - Structured logging with trace context
  - Dashboard integration
  
- **Days 4-5:** Performance optimization
  - Profile hot paths
  - Optimize context building
  - Cache KB search results
  - Reduce latency
  
- **Deliverables:**
  - ✅ Full OpenTelemetry instrumentation
  - ✅ Metrics in Grafana dashboards
  - ✅ Trace visualization in Jaeger
  - ✅ Performance improvements measured
  - ✅ Optimization report

#### Week 9: Comprehensive Testing & Documentation
- **Days 1-3:** Testing hardening
  - Edge case testing
  - Error recovery testing
  - Long-running task testing
  - Stress testing
  
- **Days 4-5:** Documentation
  - Architecture documentation
  - User guide updates
  - API documentation
  - Migration guide (v1 → v2)
  
- **Deliverables:**
  - ✅ 250+ tests passing
  - ✅ 90%+ code coverage
  - ✅ Comprehensive documentation
  - ✅ Migration guide
  - ✅ Release notes

**Phase 3 Success Criteria:**
- [ ] UX is polished and intuitive
- [ ] Observability fully integrated
- [ ] Performance meets targets
- [ ] 250+ tests passing
- [ ] Documentation complete
- [ ] Ready for production deployment

---

### Phase 4: Future Enhancements (Post-Launch)

**Deferred to future iterations:**

1. **Self-Correction Loop** (2-3 iterations)
   - Execution validation
   - Error detection and recovery
   - Iterative refinement

2. **Automatic Complexity Classification**
   - Fast model to classify task complexity
   - Auto-suggest mode based on analysis
   - Learning from user mode selections

3. **Aider-Style Repo Maps**
   - Tree-sitter full repo analysis
   - Symbol graph generation
   - Smart context inclusion

4. **Multi-Agent Expansion**
   - When tool count > 20
   - When context > 50K tokens
   - Parallel execution for independent tasks

5. **Advanced Context Management**
   - Context window utilization tracking
   - Automatic context pruning
   - Long-range dependency detection

6. **Evaluation Framework**
   - Internal benchmarks
   - Pass@1 tracking
   - Cost/quality optimization

---

## Technical Specifications

### System Requirements

**Agent Core v2:**
- Bun >= 1.0.0
- TypeScript 5.0+
- 1GB RAM minimum
- Claude CLI installed and authenticated

**VSCode Extension:**
- VS Code >= 1.80.0
- Node.js >= 18.0.0
- 500MB RAM minimum

**Knowledge Bank:**
- Python >= 3.12
- 2GB RAM minimum for indexing
- 500MB RAM for serving

### Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Editor Mode latency | < 5s to first token | p50 |
| Research phase | < 30s | p50 |
| Planning phase | < 60s | p50 |
| Implementation phase | < 5min for medium task | p50 |
| Plan approval latency | < 100ms | UI response |
| KB search latency | < 2s | p95 |
| Context build time | < 3s for 20 files | p95 |
| State save time | < 50ms | p95 |

### Cost Targets

| Operation | Model | Est. Tokens | Est. Cost |
|-----------|-------|-------------|-----------|
| Research phase | Haiku 4.5 | 3K - 10K | $0.01 - $0.04 |
| Planning phase | Opus 4 | 8K - 20K | $0.24 - $0.60 |
| Implementation | Sonnet 4.5 | 10K - 50K | $0.03 - $0.15 |
| **Total (Architect)** | Multi-model | 21K - 80K | **$0.28 - $0.79** |
| Editor mode | Sonnet 4.5 | 5K - 15K | $0.015 - $0.045 |

**Target:** Keep average task cost < $1.00

### API Contracts

**JSON-RPC Methods:**

```typescript
// Start a new task
{
  "jsonrpc": "2.0",
  "id": "req-123",
  "method": "task.start",
  "params": {
    "mode": "architect" | "editor",
    "message": string,
    "context": {
      "files": string[],
      "folders": string[],
      "selection": string
    },
    "conversationHistory": Message[]
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": "req-123",
  "result": {
    "sessionId": string,
    "state": WorkflowState
  }
}

// Approve plan
{
  "jsonrpc": "2.0",
  "id": "req-124",
  "method": "task.approve",
  "params": {
    "sessionId": string
  }
}

// Reject plan
{
  "jsonrpc": "2.0",
  "id": "req-125",
  "method": "task.reject",
  "params": {
    "sessionId": string,
    "reason": string (optional)
  }
}

// Request plan revision
{
  "jsonrpc": "2.0",
  "id": "req-126",
  "method": "task.revise",
  "params": {
    "sessionId": string,
    "feedback": string
  }
}

// Get session status
{
  "jsonrpc": "2.0",
  "id": "req-127",
  "method": "task.status",
  "params": {
    "sessionId": string
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": "req-127",
  "result": {
    "sessionId": string,
    "state": WorkflowState,
    "plan": Plan (if available),
    "execution": ExecutionResult (if available),
    "metadata": SessionMetadata
  }
}

// Cancel task
{
  "jsonrpc": "2.0",
  "id": "req-128",
  "method": "task.cancel",
  "params": {
    "sessionId": string
  }
}
```

**Streaming Events:**

Events are emitted via JSON-RPC notifications:

```typescript
// State change
{
  "jsonrpc": "2.0",
  "method": "task.stateChange",
  "params": {
    "sessionId": string,
    "state": WorkflowState,
    "timestamp": string
  }
}

// Progress update
{
  "jsonrpc": "2.0",
  "method": "task.progress",
  "params": {
    "sessionId": string,
    "phase": string,
    "progress": number (0-100),
    "message": string
  }
}

// Tool call
{
  "jsonrpc": "2.0",
  "method": "task.toolCall",
  "params": {
    "sessionId": string,
    "tool": string,
    "input": unknown,
    "output": unknown (when complete)
  }
}

// Response chunk (streaming)
{
  "jsonrpc": "2.0",
  "method": "task.chunk",
  "params": {
    "sessionId": string,
    "content": string,
    "type": "text" | "thinking" | "code" | "tool"
  }
}

// Error
{
  "jsonrpc": "2.0",
  "method": "task.error",
  "params": {
    "sessionId": string,
    "error": {
      "code": string,
      "message": string,
      "details": unknown
    }
  }
}
```

---

## Testing Strategy

### Unit Tests (Target: 150+ tests)

**Orchestrator (30 tests):**
- State machine transitions
- Mode routing logic
- Approval handling
- Session management
- Error scenarios

**Workflows (40 tests):**
- EditorWorkflow execution
- ArchitectWorkflow phases
- Research phase with KB
- Planning phase
- Implementation phase
- State transitions

**ClaudeProvider (25 tests):**
- CLI spawning
- Model selection
- Stream parsing
- Authentication detection
- Error handling

**ContextBuilder (25 tests):**
- KB search integration
- File loading
- Token estimation
- Context truncation
- Priority handling

**StateStore (20 tests):**
- TOML serialization
- Session persistence
- Plan versioning
- State recovery
- Cleanup

**PromptBuilder (10 tests):**
- Prompt templates
- Context formatting
- Tool descriptions
- System prompts

### Integration Tests (Target: 50+ tests)

**End-to-End Workflows:**
- Editor mode: simple file edit
- Editor mode: multi-file change
- Architect mode: full planning cycle
- Architect mode: plan revision
- Architect mode: plan rejection
- KB integration: search and context
- Multi-model execution

**VSCode Integration:**
- Extension activation
- Message passing
- Webview communication
- Command execution
- File watching
- Error recovery

**Knowledge Bank Integration:**
- Search during research
- Context assembly
- Result parsing
- Timeout handling
- Error scenarios

### Performance Tests (Target: 20+ tests)

**Latency Benchmarks:**
- Editor mode response time
- Research phase duration
- Planning phase duration
- Implementation phase duration
- KB search latency
- Context build time
- State save/load time

**Load Tests:**
- Concurrent sessions
- Long conversations
- Large context handling
- Memory usage over time
- Resource cleanup

### Acceptance Tests (Target: 30+ tasks)

**Real-World Tasks:**
- Add authentication to API
- Refactor module structure
- Fix security vulnerability
- Add new endpoint with tests
- Implement data validation
- Update documentation
- Add error handling
- Optimize performance
- Add logging
- Create utility function

**Success Criteria per Task:**
- Task completes successfully
- Output is correct
- Tests pass
- Cost within budget
- Time within limits
- Plan was helpful
- User experience smooth

---

## Integration Points

### Knowledge Bank (Existing)

**Search API Integration:**
```typescript
class KBClient {
  async search(params: SearchParams): Promise<SearchResult[]> {
    const response = await fetch('http://localhost:8000/v1/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: params.query,
        top_k: params.topK,
        diversity_threshold: params.diversityThreshold,
        use_reranking: params.useReranking,
        repo_name: params.repoName
      })
    })
    
    return response.json()
  }
  
  async fetchChunk(chunkId: string): Promise<Chunk> {
    const response = await fetch(`http://localhost:8000/v1/chunks/${chunkId}`)
    return response.json()
  }
  
  async fetchLines(params: FetchLinesParams): Promise<FileSlice> {
    const url = new URL('http://localhost:8000/v1/file')
    url.searchParams.set('repo_name', params.repoName)
    url.searchParams.set('file_path', params.filePath)
    url.searchParams.set('start_line', params.startLine.toString())
    url.searchParams.set('end_line', params.endLine.toString())
    
    const response = await fetch(url)
    return response.json()
  }
  
  async health(): Promise<HealthStatus> {
    const response = await fetch('http://localhost:8000/v1/health')
    return response.json()
  }
}
```

**Enhancement Opportunities:**
- Symbol search endpoint (future)
- Batch chunk retrieval
- Context-aware search
- Caching layer

### Observability (EP-1)

**OpenTelemetry Integration:**
```typescript
import { trace, context, SpanStatusCode } from '@opentelemetry/api'
import { PrometheusExporter } from '@opentelemetry/exporter-prometheus'

class ObservabilityService {
  private tracer = trace.getTracer('dolphin-agent-core-v2')
  
  async traceWorkflow<T>(
    name: string,
    fn: (span: Span) => Promise<T>
  ): Promise<T> {
    return this.tracer.startActiveSpan(name, async (span) => {
      try {
        const result = await fn(span)
        span.setStatus({ code: SpanStatusCode.OK })
        return result
      } catch (error) {
        span.setStatus({
          code: SpanStatusCode.ERROR,
          message: error.message
        })
        span.recordException(error)
        throw error
      } finally {
        span.end()
      }
    })
  }
  
  recordMetric(name: string, value: number, labels?: Record<string, string>) {
    // Prometheus metrics
    const metric = metrics.getMetric(name)
    metric.add(value, labels)
  }
  
  log(level: string, message: string, metadata: unknown) {
    // Structured logging with trace context
    const span = trace.getActiveSpan()
    const traceId = span?.spanContext().traceId
    const spanId = span?.spanContext().spanId
    
    console.log(JSON.stringify({
      timestamp: new Date().toISOString(),
      level,
      message,
      traceId,
      spanId,
      ...metadata
    }))
  }
}
```

**Metrics to Emit:**
- `dolphin_task_duration_seconds{mode, state}`
- `dolphin_task_total{mode, status}`
- `dolphin_kb_search_duration_seconds`
- `dolphin_claude_api_tokens_total{model, phase}`
- `dolphin_claude_api_cost_total{model, phase}`
- `dolphin_plan_approval_duration_seconds`
- `dolphin_plan_revisions_total`
- `dolphin_context_tokens{source}`

### VSCode Extension

**Message Passing:**
```typescript
// Extension → Agent Core
interface ExtensionMessage {
  type: 'request' | 'notification'
  id?: string
  method: string
  params: unknown
}

// Agent Core → Extension
interface AgentMessage {
  type: 'response' | 'notification'
  id?: string
  result?: unknown
  error?: ErrorObject
  method?: string
  params?: unknown
}

class MessageHandler {
  private pending = new Map<string, Deferred>()
  
  async request(message: ExtensionMessage): Promise<unknown> {
    const deferred = createDeferred()
    this.pending.set(message.id!, deferred)
    
    await this.send(message)
    
    return deferred.promise
  }
  
  notify(method: string, params: unknown): void {
    this.send({
      type: 'notification',
      method,
      params
    })
  }
  
  private async send(message: ExtensionMessage | AgentMessage): Promise<void> {
    const json = JSON.stringify(message)
    const buffer = Buffer.from(json, 'utf-8')
    const header = `Content-Length: ${buffer.length}\r\n\r\n`
    
    await this.writeToStdin(header + json)
  }
  
  onMessage(handler: (message: AgentMessage) => void): void {
    // Parse messages from stdout
    this.stdout.on('data', (chunk) => {
      this.buffer += chunk.toString()
      
      while (true) {
        const match = this.buffer.match(/Content-Length: (\d+)\r\n\r\n/)
        if (!match) break
        
        const length = parseInt(match[1])
        const start = match[0].length
        
        if (this.buffer.length < start + length) break
        
        const json = this.buffer.slice(start, start + length)
        this.buffer = this.buffer.slice(start + length)
        
        const message = JSON.parse(json)
        
        if (message.type === 'response') {
          const deferred = this.pending.get(message.id)
          if (deferred) {
            if (message.error) {
              deferred.reject(new Error(message.error.message))
            } else {
              deferred.resolve(message.result)
            }
            this.pending.delete(message.id)
          }
        } else {
          handler(message)
        }
      }
    })
  }
}
```

---

## Risk Analysis

### Technical Risks

**1. Claude CLI Reliability**
- **Risk:** CLI subprocess crashes or hangs
- **Mitigation:** 
  - Watchdog timer for subprocess
  - Automatic restart on crash
  - Fallback to API key mode
  - Extensive error handling and logging

**2. Context Window Management**
- **Risk:** Exceeding token limits or poor utilization
- **Mitigation:**
  - Token tracking throughout pipeline
  - Aggressive truncation strategies
  - Context priority system
  - Monitoring and alerting

**3. Plan Quality Variance**
- **Risk:** Plans may be too vague or too detailed
- **Mitigation:**
  - Structured plan templates
  - Plan validation logic
  - User revision capability
  - Iterative improvement from feedback

**4. Performance Degradation**
- **Risk:** Slow response times for complex tasks
- **Mitigation:**
  - Performance benchmarking
  - Optimization based on metrics
  - Caching where appropriate
  - Model selection tuning

**5. State Corruption**
- **Risk:** TOML files get corrupted
- **Mitigation:**
  - Atomic writes with temp files
  - Regular backups
  - Validation on read
  - Recovery procedures

### Process Risks

**1. Scope Creep**
- **Risk:** Adding features beyond v2 scope
- **Mitigation:**
  - Clear phase boundaries
  - Defer enhancements to future
  - Focus on core workflow
  - Regular scope reviews

**2. Testing Debt**
- **Risk:** Insufficient test coverage
- **Mitigation:**
  - Test-driven development
  - Coverage requirements per phase
  - Integration tests throughout
  - Acceptance testing

**3. Integration Breakage**
- **Risk:** Changes break existing KB or Extension
- **Mitigation:**
  - Maintain API contracts
  - Extensive integration testing
  - Backward compatibility where needed
  - Version negotiation

### Mitigation Plan

**Critical Path Items:**
1. Claude CLI subprocess spawning (Week 2)
   - Test extensively with all auth modes
   - Build robust error handling early
   
2. State persistence (Week 1)
   - Validate TOML serialization thoroughly
   - Test recovery scenarios
   
3. KB integration (Week 3)
   - Test with various search patterns
   - Handle KB unavailability gracefully
   
4. Plan approval flow (Week 5)
   - Test all user interaction paths
   - Ensure UI state sync is reliable

**Contingency Plans:**
- If CLI proves unreliable → Fallback to direct API integration
- If TOML causes issues → Switch to JSON persistence
- If KB integration is problematic → Make it optional
- If multi-model is too complex → Start with single model

---

## Success Criteria

### Functional Requirements

**Must Have (P0):**
- [ ] Editor Mode works end-to-end for simple tasks
- [ ] Architect Mode completes research → plan → approval → execute
- [ ] Plans are generated with Opus and displayed for approval
- [ ] Users can approve, reject, or request revision of plans
- [ ] Plan revisions work correctly
- [ ] KB search is integrated into research phase
- [ ] Multi-model orchestration works (Haiku/Opus/Sonnet)
- [ ] State persists across sessions in TOML
- [ ] Streaming responses work in VSCode
- [ ] CLI authentication detection works

**Should Have (P1):**
- [ ] Cost estimates shown before execution
- [ ] Token usage tracked and displayed
- [ ] Progress indicators for all phases
- [ ] Verbose plan drilldown available
- [ ] Error recovery and retry logic
- [ ] Observability integration (metrics, traces, logs)
- [ ] Performance meets targets
- [ ] 250+ tests passing with 90%+ coverage

**Nice to Have (P2):**
- [ ] Plan comparison across versions
- [ ] Mode suggestions based on task
- [ ] Context optimization
- [ ] Advanced error diagnostics
- [ ] Export plan as markdown

### Quality Requirements

**Performance:**
- Editor mode: < 5s to first token (p50)
- Research phase: < 30s (p50)
- Planning phase: < 60s (p50)
- KB search: < 2s (p95)
- State operations: < 100ms (p95)

**Reliability:**
- 99% success rate for simple tasks
- 95% success rate for complex tasks
- < 1% crash rate
- Graceful degradation when KB unavailable

**Cost:**
- Average task cost < $1.00
- Research phase < $0.05
- Planning phase < $0.60
- Implementation phase < $0.40

**Quality:**
- 250+ unit tests passing
- 50+ integration tests passing
- 30+ acceptance tests passing
- 90%+ code coverage
- Zero P0 bugs at launch

### User Experience Requirements

**Usability:**
- Mode selection intuitive and clear
- Plan approval flow smooth and fast
- Progress always visible
- Errors explained with remediation
- Costs transparent

**Documentation:**
- Architecture doc complete
- User guide updated
- API reference available
- Migration guide (v1 → v2)
- Troubleshooting guide

### Acceptance Criteria

**Launch Readiness:**
1. All P0 functional requirements met
2. Performance targets achieved
3. Quality gates passed (tests, coverage)
4. Documentation complete
5. Observability integrated
6. Real-world task validation complete
7. User feedback incorporated
8. Known issues documented
9. Migration path clear
10. Team sign-off

---

## Next Steps

### Immediate Actions

1. **Review & Approve Plan**
   - Team review of this document
   - Address any questions or concerns
   - Finalize architecture decisions
   - Get stakeholder approval

2. **Environment Setup**
   - Create agent-core-v2 directory structure
   - Set up development environment
   - Configure testing infrastructure
   - Set up observability (if not done)

3. **Sprint Planning**
   - Break down Phase 1 into daily tasks
   - Assign ownership
   - Set up tracking (GitHub issues/project)
   - Schedule daily standups

4. **Kick-off Meeting**
   - Review architecture with team
   - Discuss technical approach
   - Clarify roles and responsibilities
   - Set communication norms

### Week 1 Kickoff (Ready to Start)

**Day 1:**
- Project setup and scaffolding
- Core interfaces defined
- TypeScript configuration
- Initial commit

**Day 2:**
- Orchestrator skeleton
- State machine implementation
- Basic test framework
- JSON-RPC scaffolding

**Day 3:**
- StateStore TOML implementation
- Session persistence
- Plan storage
- Unit tests

**Day 4:**
- JSON-RPC message handlers
- Extension communication layer
- Message framing
- Integration tests

**Day 5:**
- Review and refinement
- Bug fixes
- Documentation updates
- Week 2 planning

---

## Appendix

### Key Research References

1. **SWE-bench Verified Results:**
   - mini-SWE-agent: 65% with 100 lines of Python
   - Agentless 1.5: 50.8% with 3-phase workflow
   - Key insight: Simple architectures outperform complex ones

2. **AlphaCodium Study:**
   - Planning improves GPT-4 from 19% → 44% on CodeContests
   - 40-50% performance degradation without planning
   - Two-phase workflow now standard

3. **AgentCoder:**
   - 96.3% on HumanEval with 3-agent system
   - Separate test designer prevents biased tests
   - Iterative refinement until tests pass

4. **Aider Architecture:**
   - Repo maps provide huge context efficiency
   - Unified diff format reduces lazy coding
   - Tree-sitter AST superior to pure embeddings

5. **Claude Code Workflow:**
   - Research → Plan → Code → Validate proven effective
   - Plan mode (read-only) separates concerns
   - Extended thinking for complex reasoning
   - User approval gates build trust

### Glossary

- **Architect Mode:** Structured workflow with planning phase for complex tasks
- **Editor Mode:** Fast-path direct execution for simple tasks
- **Knowledge Bank (KB):** Dolphin's semantic code search system
- **Orchestrator:** Core state machine managing workflow execution
- **Plan:** Structured implementation plan generated in architect mode
- **Research Phase:** Initial exploration phase using KB search and file reading
- **State Store:** TOML-based persistence layer for conversations and plans
- **Workflow:** Sequence of phases (research, plan, implement, validate)

### Contact & Support

**Project Lead:** Taylor  
**Documentation:** This document + ARCHITECTURE.md + GUIDE.md  
**Repository:** https://github.com/plasticbeachllc/dolphin  
**Issues:** GitHub Issues

---

**Document Status:** ✅ Complete - Ready for Implementation  
**Next Review:** After Phase 1 completion  
**Version:** 1.0  
**Date:** 2025-11-10
