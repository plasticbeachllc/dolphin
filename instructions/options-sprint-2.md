# Sprint 2 Enhancement Options - Dolphin Stack

*"The ocean of code is vast - let's build better sonar to navigate it"*

## 🎯 Foundation First

### 1. Hybrid Search & Reranking
**Flavor**: *"When keywords and semantics join forces"*  
Give our retriever the best of both worlds - keyword matching for precision and semantic search for conceptual understanding.

**Interface Spec**:
```yaml
# config.yaml additions
retrieval:
  strategy: "hybrid"  # hybrid|vector|keyword
  rrf_k: 60           # Reciprocal Rank Fusion parameter
  reranker: 
    enabled: true
    model: "local"    # local|cohere (future: openai)

# API enhancement
POST /v1/search:
  request:
    strategy: "hybrid"  # Optional override
    use_reranker: true
```

**CLI Commands**:
```bash
kb optimize-search --strategy hybrid --enable-reranker
```

### 2. Watch Mode & Incremental Indexing  
**Flavor**: *"Your codebase changes, your knowledge stays current"*  
Stop manual re-indexing. Watch file systems and git for changes, updating only what's modified.

**Interface Spec**:
```yaml
# config.yaml
watch:
  enabled: true
  poll_interval: 30  # seconds
  ignore_temp_files: true

# New CLI commands
kb watch [repo] [--poll-interval 30]
kb sync [repo] [--since "2 hours ago"]
```

**Implementation Notes**:
- File system events via `watchdog`
- Git-aware change detection
- Batched updates every 5 minutes or 50 files

## 🚀 Enhanced Intelligence

### 3. Query Understanding & Routing
**Flavor**: *"Knowing what you're really looking for"*  
Automatically detect query intent and choose the right search strategy - code navigation vs conceptual questions vs error lookup.

**Interface Spec**:
```python
# Query classification results
{
  "intent": "code_navigation",  # code_navigation|conceptual|error|api_usage
  "confidence": 0.87,
  "suggested_strategy": "symbol_search",
  "detected_entities": ["initScheduler", "function"]
}

# Enhanced search response
{
  "hits": [...],
  "query_analysis": {
    "interpretation": "Looking for function implementation",
    "suggested_follow_up": "Would you like to see callers of this function?"
  }
}
```

### 4. Cross-Repo Code Intelligence
**Flavor**: *"Seeing the forest through the trees"*  
Connect the dots across repositories - function call graphs, API usage patterns, and dependency relationships.

**Interface Spec**:
```python
# New API endpoints
POST /v1/call-graph:
  request: {"symbol": "initScheduler", "repos": ["infra", "services"]}
  response: {"callers": [...], "callees": [...]}

POST /v1/usage-patterns:
  request: {"pattern": "stripe.webhooks", "repos": ["payments"]}
  response: {"usages": [...], "variants": [...]}
```

**CLI Integration**:
```bash
kb graph --symbol initScheduler --format mermaid
kb find-usages --pattern "database.pool" --repos backend
```

## 🧠 Advanced Workflows

### 5. Planner-Executor Pattern
**Flavor**: *"Breaking down complex questions into simple searches"*  
For complex multi-part questions, automatically plan a retrieval strategy and execute it step by step.

**Interface Spec**:
```python
POST /v1/plan-search:
  request: {"query": "How do we handle payment failures across microservices?"}
  response: {
    "plan": [
      {"step": 1, "query": "payment service error handling", "strategy": "hybrid"},
      {"step": 2, "query": "circuit breaker pattern implementation", "strategy": "conceptual"},
      {"step": 3, "query": "monitoring alert configuration", "strategy": "config_search"}
    ],
    "estimated_complexity": "high"
  }
```

### 6. Code Change Impact Analysis
**Flavor**: *"Predicting the ripple effects of your changes"*  
Understand what code will be affected by proposed changes before you make them.

**Interface Spec**:
```python
POST /v1/analyze-impact:
  request: {
    "changes": [
      {"file": "src/database/schema.ts", "change_type": "modification"},
      {"file": "src/api/users.ts", "change_type": "addition"}
    ],
    "repos": ["backend"]
  }
  response: {
    "affected_components": [...],
    "risk_level": "medium",
    "suggested_reviewers": ["@backend-team"]
  }
```

## 🔧 Developer Experience

### 7. Natural Language Code Navigation
**Flavor**: *"Talk to your codebase like a colleague"*  
Replace file paths with natural language descriptions for navigation.

**Interface Spec**:
```python
POST /v1/navigate:
  request: {"description": "user authentication middleware"}
  response: {
    "matches": [
      {"file": "src/middleware/auth.ts", "confidence": 0.94, "description": "JWT authentication middleware"},
      {"file": "src/utils/oauth.ts", "confidence": 0.87, "description": "OAuth2 flow implementation"}
    ]
  }
```

### 8. Error Diagnosis Assistant
**Flavor**: *"From stack trace to solution in seconds"*  
Connect error messages to relevant code, documentation, and historical fixes.

**Interface Spec**:
```python
POST /v1/diagnose-error:
  request: {
    "error_message": "TypeError: Cannot read properties of undefined",
    "stack_trace": "...",
    "file_context": "src/components/UserProfile.tsx"
  }
  response: {
    "likely_causes": [...],
    "relevant_code": [...],
    "historical_fixes": [...],
    "documentation": [...]
  }
```

## 🏗️ Infrastructure Evolution

### 9. Multi-Model Embedding Bridge
**Flavor**: *"Future-proofing our vector foundations"*  
Smooth transition between embedding models without losing search quality.

**Interface Spec**:
```yaml
# config.yaml
embeddings:
  active_model: "openai-small"
  fallback_models: ["local-all-minilm", "cohere-english"]
  migration:
    auto_migrate: false
    parallel_indexing: true

# CLI commands
kb migrate-embeddings --from openai-small --to local-all-minilm
kb compare-models --models openai-small local-all-minilm
```

### 10. Distributed Knowledge Graph
**Flavor**: *"Mapping the relationships in your code universe"*  
Build a graph of how code entities relate to each other across the entire codebase.

**Interface Spec**:
```python
# Graph schema
Node: {id, type, name, repo, file, line}
Edge: {source, target, relationship, strength}

# API endpoints
POST /v1/graph/query:
  request: {"pattern": "Component -> uses -> Service"}
  response: {"subgraphs": [...], "insights": [...]}

GET /v1/graph/visualization/{query_id}:
  response: Mermaid/Graphviz representation
```

## 🎚️ Implementation Sequence

**Foundation Layer** (build first):
- Hybrid Search & Reranking
- Watch Mode & Incremental Indexing

**Intelligence Layer** (build next):  
- Query Understanding & Routing
- Natural Language Code Navigation
- Error Diagnosis Assistant

**Advanced Layer** (build after):
- Cross-Repo Code Intelligence
- Code Change Impact Analysis
- Planner-Executor Pattern

**Evolution Layer** (long-term):
- Multi-Model Embedding Bridge
- Distributed Knowledge Graph

## 🚀 Implementation Sequence

**Sequence 1: Core Retrieval**
- Hybrid Search & Reranking
- Watch Mode & Incremental Indexing

**Sequence 2: Smart Interaction**  
- Query Understanding & Routing
- Natural Language Code Navigation
- Error Diagnosis Assistant

**Sequence 3: Deep Analysis**
- Cross-Repo Code Intelligence
- Code Change Impact Analysis

**Sequence 4: Advanced Systems**
- Planner-Executor Pattern
- Distributed Knowledge Graph
- Multi-Model Embedding Bridge

## 💡 Getting Started

Start with Sequence 1 to build your foundation:

```bash
# Begin with hybrid search enhancement
uv run kb optimize-search --enable-hybrid --enable-reranker

# Then add automated indexing  
uv run kb watch infra --poll-interval 30
```

Which sequence shall we begin with? 🌊
