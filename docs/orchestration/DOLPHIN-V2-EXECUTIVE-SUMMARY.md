# Dolphin v2 Orchestration - Executive Summary

**Document Version:** 1.0  
**Date:** 2025-11-10  
**Status:** Ready for Implementation

---

## Overview

This document provides a quick reference to the comprehensive v2 orchestration architecture project plan. The full plan is available in `DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md`.

---

## Key Architectural Decisions

### 1. **Single-Agent with Adaptive Workflow** ✅
- Start with single-agent architecture
- Two modes: Editor (fast) and Architect (planning)
- User manually selects mode in v2
- Architecture supports future multi-agent expansion

### 2. **Multi-Model Orchestration** ✅
- **Haiku 4.5** → Research/exploration (fast, cost-effective)
- **Opus 4** → Planning/architecture (best reasoning)
- **Sonnet 4.5** → Coding/implementation (balanced)
- Target cost: <$1.00 per task

### 3. **Claude CLI Subprocess Pattern** ✅
- Use Kilocode-proven subprocess spawning
- Zero credential management (CLI handles auth)
- Supports both subscription and API key modes
- Robust error handling and recovery

### 4. **TOML State Persistence** ✅
- Human-readable session storage
- Plan versioning and revision tracking
- Atomic writes to prevent corruption
- Clean separation of metadata and content

### 5. **Research-Backed Workflow** ✅
```
Architect Mode:
1. Research (Haiku) → KB search + file exploration
2. Planning (Opus) → Generate plan.md
3. Approval → User reviews and decides
4. Implementation (Sonnet) → Execute approved plan
5. Validation → Run tests (future)

Editor Mode:
1. Task → Direct execution with Sonnet
```

### 6. **Deep Knowledge Bank Integration** ✅
- KB search as first-class citizen
- Research phase automatically searches KB
- Planning prompts explicitly guide Claude to use KB tools
- Context assembly prioritizes KB results

### 7. **User Control & Transparency** ✅
- Users approve plans before execution
- Concise plan view with optional verbose drilldown
- Cost/token estimates shown upfront
- Plan revision capability with feedback

### 8. **Observability Integration** ✅
- Integrate with existing EP-1 infrastructure
- OpenTelemetry spans for all workflows
- Prometheus metrics for key operations
- Structured logging with trace context

---

## System Architecture at a Glance

```
┌─────────────────┐
│ VSCode Extension│
│  (Svelte UI)    │
└────────┬────────┘
         │ JSON-RPC
         ▼
┌─────────────────┐
│   Orchestrator  │◄─── Core State Machine
│                 │     • Mode routing
│                 │     • Approval flow
│                 │     • State persistence
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌─────────┐ ┌──────────────┐
│ Editor  │ │  Architect   │
│Workflow │ │  Workflow    │
└────┬────┘ └──────┬───────┘
     │             │
     │    ┌────────┴─────────┐
     │    │                  │
     ▼    ▼                  ▼
┌──────────────┐  ┌────────────────┐
│ClaudeProvider│  │ContextBuilder  │
│(Multi-Model) │  │ (KB Integration)│
└──────────────┘  └────────────────┘
     │                    │
     ▼                    ▼
┌──────────────┐  ┌────────────────┐
│  Claude CLI  │  │Knowledge Bank  │
│(Subprocess)  │  │(Semantic Search)│
└──────────────┘  └────────────────┘
```

---

## Implementation Timeline

### Phase 1: Foundation (Weeks 1-3)
**Goal:** Build core infrastructure + Editor Mode

- Week 1: Orchestrator + StateStore + JSON-RPC
- Week 2: ClaudeProvider + EditorWorkflow
- Week 3: ContextBuilder + KB integration

**Deliverable:** Editor Mode working end-to-end

### Phase 2: Architect Workflow (Weeks 4-6)
**Goal:** Implement full planning workflow

- Week 4: Research + Planning phases
- Week 5: Approval flow + UI integration
- Week 6: Implementation phase + E2E testing

**Deliverable:** Architect Mode working end-to-end

### Phase 3: Polish & Optimization (Weeks 7-9)
**Goal:** Refine UX and performance

- Week 7: UX refinement + mode selection
- Week 8: Observability integration + optimization
- Week 9: Testing hardening + documentation

**Deliverable:** Production-ready v2

---

## Success Criteria

### Functional (Must-Have)
- [ ] Editor Mode: simple tasks < 5s
- [ ] Architect Mode: research → plan → approval → execute
- [ ] Plans generated with Opus, displayed for approval
- [ ] Plan revision works with user feedback
- [ ] KB search integrated in research phase
- [ ] Multi-model orchestration functional
- [ ] State persists in TOML correctly
- [ ] Streaming responses in VSCode

### Quality (Must-Have)
- [ ] 250+ tests passing
- [ ] 90%+ code coverage
- [ ] Performance targets met
- [ ] Average cost < $1.00 per task
- [ ] Observability fully integrated

### User Experience (Must-Have)
- [ ] Mode selection intuitive
- [ ] Plan approval flow smooth
- [ ] Costs transparent
- [ ] Progress always visible
- [ ] Errors well-explained

---

## Key Technical Specifications

### Performance Targets
| Metric | Target |
|--------|--------|
| Editor Mode | < 5s to first token |
| Research Phase | < 30s |
| Planning Phase | < 60s |
| KB Search | < 2s |
| State Save | < 100ms |

### Cost Targets
| Operation | Model | Cost |
|-----------|-------|------|
| Research | Haiku 4.5 | $0.01-$0.04 |
| Planning | Opus 4 | $0.24-$0.60 |
| Implementation | Sonnet 4.5 | $0.03-$0.15 |
| **Total** | Multi-model | **$0.28-$0.79** |

### Test Coverage Targets
- Unit tests: 150+
- Integration tests: 50+
- Acceptance tests: 30+
- Code coverage: 90%+

---

## What's Deferred to Future

These are explicitly **not** in v2 scope:

1. **Self-Correction Loop** (2-3 iterations)
   - Execution validation
   - Error detection and recovery
   - Iterative refinement

2. **Automatic Complexity Classification**
   - Fast model to classify tasks
   - Auto-suggest mode
   - Learning from user selections

3. **Aider-Style Repo Maps**
   - Tree-sitter full repo analysis
   - Symbol graph generation
   - Smart context inclusion

4. **Multi-Agent Orchestration**
   - Parallel execution
   - Specialized agents
   - Context isolation

5. **Advanced Context Management**
   - Automatic context pruning
   - Long-range dependency detection
   - Context window optimization

6. **Evaluation Framework**
   - Internal benchmarks
   - Pass@1 tracking
   - Cost/quality optimization

---

## Critical Path Items

### Week 1-2 (Make or Break)
1. **Claude CLI Subprocess Spawning**
   - Must work reliably across auth modes
   - Robust error handling essential
   - Fallback plan: Direct API integration

2. **State Persistence (TOML)**
   - Validate serialization thoroughly
   - Test corruption scenarios
   - Fallback plan: Switch to JSON

3. **JSON-RPC Communication**
   - Message framing must be solid
   - Handle backpressure correctly
   - Test concurrent requests

### Week 3-4 (Core Functionality)
4. **KB Integration**
   - Test various search patterns
   - Handle KB unavailability gracefully
   - Fallback plan: Make KB optional

5. **Multi-Model Execution**
   - Verify model selection works
   - Test all three models (Haiku/Opus/Sonnet)
   - Fallback plan: Single model (Sonnet)

### Week 5-6 (User Experience)
6. **Plan Approval Flow**
   - Test all user interaction paths
   - Ensure UI state sync is reliable
   - Handle edge cases (timeouts, crashes)

---

## Risk Mitigation

### Technical Risks

**Risk:** Claude CLI subprocess crashes or hangs  
**Mitigation:**
- Watchdog timer for subprocess
- Automatic restart on crash
- Fallback to API key mode
- Extensive logging

**Risk:** Context exceeds token limits  
**Mitigation:**
- Token tracking throughout
- Aggressive truncation strategies
- Context priority system
- Monitoring and alerts

**Risk:** Plan quality varies widely  
**Mitigation:**
- Structured plan templates
- Plan validation logic
- User revision capability
- Iterative improvement

**Risk:** Performance degradation  
**Mitigation:**
- Performance benchmarking
- Optimization based on metrics
- Caching strategies
- Model selection tuning

**Risk:** State corruption  
**Mitigation:**
- Atomic writes with temp files
- Regular backups
- Validation on read
- Recovery procedures

---

## Open Questions & Decisions Needed

### 1. Extended Thinking Control
**Question:** How do we trigger extended thinking with Claude CLI?  
**Options:**
- A) Include "think hard" in prompt
- B) CLI flag (research if available)
- C) Model-specific prompting

**Recommendation:** Start with A (prompt-based), research B

### 2. Tool Description Format
**Question:** How does Claude CLI handle tool descriptions?  
**Options:**
- A) Embed in prompt as text
- B) Use MCP protocol (if CLI supports)
- C) Custom JSON format

**Recommendation:** Start with A (prompt-based), likely what CLI expects

### 3. Stream Parsing Format
**Question:** What format does Claude CLI output?  
**Action Required:**
- Test with actual CLI to determine format
- May be JSON lines, markdown, or mixed
- Build robust parser for observed format

### 4. Metrics Collection
**Question:** How invasive should telemetry be?  
**Recommendation:** 
- Always-on for core metrics (latency, cost, success)
- Opt-in for detailed traces
- No PII in logs/metrics

### 5. Plan Validation
**Question:** Should we validate plans programmatically?  
**Recommendation:**
- Basic validation (has required sections)
- Defer complex validation to user review
- Learn from revision feedback

---

## Integration Checklist

### Knowledge Bank Integration
- [x] API client implementation
- [x] Search endpoint integration
- [x] Chunk retrieval
- [x] File slice fetching
- [x] Health check
- [ ] Context assembly with KB results
- [ ] Token estimation for KB results
- [ ] KB unavailability handling

### VSCode Extension Integration
- [x] JSON-RPC communication layer
- [x] Message framing (Content-Length)
- [x] Webview message passing
- [ ] Mode selection UI
- [ ] Plan approval UI
- [ ] Progress indicators
- [ ] Streaming response display
- [ ] Error handling and recovery

### Observability Integration
- [ ] OpenTelemetry spans
- [ ] Prometheus metrics
- [ ] Structured logging
- [ ] Grafana dashboards
- [ ] Alert rules
- [ ] Cost tracking

---

## Quick Start Guide

### For Developers Starting Implementation

**Step 1: Environment Setup**
```bash
# Create agent-core-v2 directory
mkdir -p agent-core-v2/src/{orchestrator,workflows,claude,context,state}

# Install dependencies
cd agent-core-v2
bun init
bun add zod @opentelemetry/api @opentelemetry/sdk-node
bun add -d @types/node vitest
```

**Step 2: Define Core Interfaces**
```typescript
// src/types/index.ts
export type WorkflowMode = 'editor' | 'architect'
export type WorkflowState = 'idle' | 'researching' | 'planning' | 'awaiting_approval' | 'executing' | 'complete'

export interface TaskInput {
  mode: WorkflowMode
  message: string
  context: ContextHints
}

// ... (see full plan for complete interfaces)
```

**Step 3: Implement Orchestrator**
```typescript
// src/orchestrator/orchestrator.ts
export class Orchestrator {
  async startTask(input: TaskInput): Promise<TaskSession> {
    // Implementation per plan
  }
}
```

**Step 4: Write Tests First**
```typescript
// tests/orchestrator.test.ts
describe('Orchestrator', () => {
  it('should create session for editor mode', async () => {
    // Test implementation
  })
})
```

---

## Reference Links

### Key Documents
- **Full Project Plan:** `DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md` (this directory)
- **Research Synthesis:** `/mnt/project/State-of-the-Art_Agent_Orchestration_Architectures_for_Coding_Assistants__Research_Synthesis_for_Dolphin_v2.md`
- **Claude Code Research:** `/mnt/project/CLAUDE-CODE-INTEGRATION-RESEARCH.md`
- **Current Architecture:** `/mnt/project/ARCHITECTURE.md`
- **Strategic Projects:** `/mnt/project/strategic-improvement-projects.md`

### External References
- Aider: https://github.com/Aider-AI/aider
- Kilocode: https://github.com/Kilo-Org/kilocode
- Claude Code: https://github.com/anthropics/claude-code
- Cline: https://github.com/cline/cline

---

## Contact & Next Steps

**Status:** ✅ Plan Complete - Ready to Begin Implementation

**Next Actions:**
1. Review this plan and full document
2. Address any questions or concerns
3. Set up development environment
4. Begin Phase 1, Week 1, Day 1
5. Daily standups to track progress

**Questions?** Refer to full plan or reach out to project lead.

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-10  
**Ready for:** Implementation Kickoff
