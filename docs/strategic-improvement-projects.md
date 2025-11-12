# Dolphin Strategic Improvement & Enhancement Projects

**Document Version**: 1.0
**Date**: 2025-11-11
**Status**: Proposal
**Codebase Version**: 0.1.13

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Project Categories](#project-categories)
3. [Enhancement Projects](#enhancement-projects)
   - [EP-1: Production Observability & Monitoring] (#ep-1-production-observability--monitoring) ✅
   - [EP-2: Intelligent Query Understanding Layer](#ep-2-intelligent-query-understanding-layer)
   - [EP-3: Advanced Code Graph Intelligence](#ep-3-advanced-code-graph-intelligence) ✅
   - [EP-4: Multi-Repository Cross-Intelligence](#ep-4-multi-repository-cross-intelligence)
   - [EP-5: Evaluation & Quality Assurance Framework](#ep-5-evaluation--quality-assurance-framework) ✅
   - [EP-6: Performance Optimization Suite](#ep-6-performance-optimization-suite) ✅
   - [EP-7: Enhanced Developer Experience](#ep-7-enhanced-developer-experience)
   - [EP-8: Enterprise-Grade Security & Compliance](#ep-8-enterprise-grade-security--compliance)
   - [EP-9: Web-Based Knowledge Portal](#ep-9-web-based-knowledge-portal)
   - [EP-10: Collaborative Features & Team Intelligence](#ep-10-collaborative-features--team-intelligence)
4. [Prioritization Matrix](#prioritization-matrix)
5. [Implementation Roadmap](#implementation-roadmap)

---

## Executive Summary

Dolphin has achieved beta maturity with a solid foundation: 243+ passing tests, production-ready core components, and a well-architected multi-layer system. This document proposes **10 strategic enhancement projects** designed to transform Dolphin from an experimental tool into a production-grade enterprise platform.

### Current State Analysis

**Strengths:**

- ✅ Robust indexing pipeline with 191+ Python tests
- ✅ Modern tech stack (FastAPI, Bun, Svelte, LanceDB)
- ✅ Comprehensive language support (Python, TS, JS, MD, SQL, Svelte)
- ✅ Advanced retrieval (hybrid search, MMR, cross-encoder reranking)
- ✅ Rich VSCode integration with beautiful UI

**Gaps Identified:**

- ⚠️ Limited production observability (no metrics, tracing, or alerting)
- ⚠️ Query understanding is basic (no intent classification or routing)
- ⚠️ Code graph underutilized (no impact analysis or visualization)
- ⚠️ No evaluation framework (can't measure improvements objectively)
- ⚠️ Performance optimization is manual (no automatic tuning)
- ⚠️ Enterprise features missing (RBAC, audit logs, SSO)
- ⚠️ Web UI limited to VSCode (no standalone portal)
- ⚠️ Collaboration features absent (no team sharing or annotations)

### Strategic Vision

Transform Dolphin into the **premier AI-enabled code intelligence platform** by:

1. **Production-grade reliability** with observability and monitoring
2. **Intelligent search** with query understanding and routing
3. **Deep code intelligence** leveraging graph analysis
4. **Team collaboration** enabling shared knowledge and insights
5. **Enterprise readiness** with security, compliance, and scalability

---

## Project Categories

Projects are organized into four strategic categories:

1. **Foundation** - Core infrastructure improvements (observability, security, performance)
2. **Intelligence** - AI/ML capabilities (query understanding, code graph, evaluation)
3. **Experience** - User-facing enhancements (DX, UI, collaboration)
4. **Enterprise** - Production deployment features (scaling, compliance, monitoring)

---

## Enhancement Projects

### EP-1: Production Observability & Monitoring

**Category**: Foundation
**Priority**: High
**Effort**: Medium (4-6 weeks)
**Impact**: High

#### Vision

Create a comprehensive observability suite that provides real-time insights into Dolphin's performance, health, and usage patterns. Enable proactive issue detection, performance bottleneck identification, and data-driven optimization decisions.

#### Business Value

- **Operational Excellence**: Reduce MTTR (Mean Time To Recovery) by 80%
- **Performance Optimization**: Identify and fix bottlenecks with data
- **Cost Control**: Track embedding costs and usage patterns
- **User Satisfaction**: Proactively address issues before users report them

#### Broad Specification

**1. Metrics Collection Layer**

- **KB API Metrics** (Python/FastAPI)

  - Request counts by endpoint, status code, repo
  - Latency histograms (p50, p95, p99) per endpoint
  - Search-specific metrics: ANN parameters, result counts, MMR application
  - Embedding metrics: tokens processed, API latency, cost per request
  - Database metrics: SQLite query time, LanceDB vector operations
  - Error rates and types

- **Agent Core Metrics** (TypeScript/Bun)

  - Conversation lifecycle: creation, duration, message counts
  - Tool execution: KB searches, file operations, success/failure rates
  - Claude API: token usage, latency, costs
  - IPC communication: message queue depth, backpressure events

- **VSCode Extension Metrics** (TypeScript)
  - User interactions: command usage, webview engagement
  - File watcher events: sync operations, drift detections
  - Crash recovery: frequency, recovery success rate
  - Performance: webview render time, extension activation time

**2. Distributed Tracing**

- Implement OpenTelemetry for cross-component trace propagation
- Trace full request lifecycle: VSCode → Agent → KB → LanceDB
- Correlation IDs already exist - enhance with span context
- Visualize trace waterfalls in Jaeger or Zipkin

**3. Structured Logging Enhancement**

- Standardize JSONL logging across all components
- Add trace context (trace_id, span_id) to all logs
- Log levels with proper severity (DEBUG, INFO, WARN, ERROR)
- Log aggregation and search (Loki or ELK stack)

**4. Health Checks & Alerting**

- Enhanced `/v1/health` endpoint with detailed component status
- Readiness vs. liveness probes for Kubernetes
- Alert rules for critical metrics (error rate >5%, latency >2s)
- Dead man's switch for indexing pipeline

**5. Dashboards**

- Grafana dashboards for real-time monitoring
- Pre-built panels: system health, search performance, costs
- User activity dashboards for VSCode extension usage
- Capacity planning views (index size growth, query volume trends)

**6. Cost Tracking & Budget Management**

- Real-time embedding cost calculation and accumulation
- Per-repo cost tracking and budgets
- Cost anomaly detection (sudden spikes)
- Cost projection and forecasting

#### Implementation Phases

**Phase 1: Core Metrics (2 weeks)**

- Add Prometheus metrics to KB API
- Implement OpenTelemetry in Agent Core
- Basic Grafana dashboards

**Phase 2: Distributed Tracing (2 weeks)**

- OpenTelemetry spans across components
- Jaeger deployment and integration
- Trace-to-log correlation

**Phase 3: Advanced Features (2 weeks)**

- Alerting rules and notifications
- Cost tracking enhancements
- Production deployment guides

#### Technical Considerations

**Questions to Answer:**

1. Should metrics be opt-in or always-on? (Recommend: always-on with privacy controls)
2. Which backend: Prometheus + Grafana, DataDog, New Relic? (Recommend: Prometheus for self-hosted)
3. How to handle PII in logs and traces? (Recommend: automatic scrubbing of query content)
4. Metrics retention policy? (Recommend: 30 days raw, 1 year aggregated)
5. Should metrics be exposed in VSCode extension UI? (Recommend: yes, lightweight health indicator)
6. How to track multi-tenant usage if deployed centrally? (Recommend: repo_name label on all metrics)

**Technology Stack:**

- **Metrics**: Prometheus (Python client for FastAPI, prom-client for Node/Bun)
- **Tracing**: OpenTelemetry with Jaeger backend
- **Logging**: Structured JSON to stdout, aggregated by Loki or ELK
- **Dashboards**: Grafana with pre-built Dolphin dashboards
- **Alerting**: Prometheus Alertmanager or PagerDuty integration

**Success Criteria:**

- [ ] All API endpoints emit latency and error metrics
- [ ] Full-stack traces for 100% of search requests
- [ ] Grafana dashboard showing 10+ key metrics
- [ ] Alert firing on synthetic test failures
- [ ] Cost tracking accurate to within $0.01

---

### EP-2: Intelligent Query Understanding Layer

**Category**: Intelligence
**Priority**: High
**Effort**: Large (8-12 weeks)
**Impact**: Very High

#### Vision

Implement an AI-powered query understanding layer that interprets user intent, classifies query types, and intelligently routes queries to optimal retrieval strategies. Transform raw natural language queries into structured search plans that dramatically improve result relevance.

#### Business Value

- **Relevance Improvement**: Increase MRR by 30-50% through better query interpretation
- **User Satisfaction**: Reduce "no results" scenarios by 80%
- **Query Efficiency**: Reduce unnecessary searches through caching and deduplication
- **Intelligent Routing**: Match queries to optimal retrieval strategies

#### Broad Specification

**1. Query Classification**

Classify queries into intent categories:

- **Code Lookup**: Finding specific functions, classes, or variables

  - Example: "where is the authentication handler?"
  - Strategy: Exact + fuzzy symbol search, prioritize definitions

- **Conceptual Search**: Understanding how something works

  - Example: "how does caching work in this project?"
  - Strategy: Semantic search across related files, include documentation

- **Bug Investigation**: Finding potential issues or error sources

  - Example: "what could cause a null pointer error in the parser?"
  - Strategy: Search error handling code, related call paths

- **API Discovery**: Finding available APIs or interfaces

  - Example: "what REST endpoints are available?"
  - Strategy: Search decorators, route definitions, OpenAPI specs

- **Example Finding**: Locating usage examples

  - Example: "show me how to use the SearchBackend class"
  - Strategy: Search test files, example directories, README code blocks

- **Dependency Tracking**: Understanding relationships
  - Example: "what modules depend on the database layer?"
  - Strategy: Code graph traversal, import analysis

**2. Query Expansion & Rewriting**

- **Synonym Expansion**: "DB" → ["database", "db", "sqlite", "lancedb"]
- **Acronym Resolution**: "ML" → "machine learning", "AST" → "abstract syntax tree"
- **Contextual Enhancement**: Add repo-specific terminology from config
- **Entity Recognition**: Extract and emphasize key entities (file names, symbols)
- **Query Refinement**: Suggest improvements for unclear queries

**3. Multi-Stage Retrieval Orchestration**

Implement query plans that combine multiple retrieval strategies:

```
Query: "How is authentication implemented?"

Plan:
  1. Semantic search for ["authentication", "auth", "login", "credentials"]
  2. Symbol search for class names matching "*Auth*"
  3. Graph traversal from auth entry points
  4. Filter to files in security-related paths
  5. Re-rank by file centrality in call graph
  6. Deduplicate and present top 10
```

**4. Contextual Priors & Personalization**

- **Workspace Context**: Favor recently edited files
- **Conversation History**: Remember previous queries in session
- **User Preferences**: Learn from click-through data
- **Project Structure**: Understand repo organization (monorepo detection)

**5. Query Feedback Loop**

- **Implicit Signals**: Track which results users open or copy
- **Explicit Feedback**: Thumbs up/down on search results
- **Query Reformulation**: Detect when users rephrase and learn
- **A/B Testing**: Compare query strategies and measure impact

#### Implementation Phases

**Phase 1: Query Classification (3 weeks)**

- Build training dataset from existing queries
- Fine-tune lightweight classifier (DistilBERT or similar)
- Integrate classification into search pipeline
- A/B test against baseline

**Phase 2: Query Expansion (2 weeks)**

- Build domain-specific synonym dictionary
- Implement acronym resolver with code-aware logic
- Add contextual query rewriting
- Measure expansion impact on recall

**Phase 3: Multi-Stage Retrieval (4 weeks)**

- Design query plan DSL
- Implement orchestration engine
- Build strategy library (5-10 common patterns)
- Optimize plan selection

**Phase 4: Feedback & Personalization (3 weeks)**

- Click-through tracking infrastructure
- Personalization model (simple ranking adjustment)
- Online learning pipeline
- Privacy controls

#### Technical Considerations

**Questions to Answer:**

1. **Model Selection**: Should we fine-tune a model or use GPT-4 for classification?

   - Option A: Fine-tuned DistilBERT (fast, cheap, private)
   - Option B: GPT-4 few-shot (accurate, expensive, requires API)
   - Recommendation: Start with GPT-4, migrate to fine-tuned model at scale

2. **Query Caching**: How long should query results be cached?

   - Recommendation: 5 minutes for identical queries, 1 hour for similar queries

3. **Privacy**: Should we store query history?

   - Recommendation: Local-only with opt-in telemetry for improvement

4. **Fallback Strategy**: What if classification fails?

   - Recommendation: Default to semantic search with full recall

5. **Performance Target**: Maximum latency overhead from query understanding?

   - Recommendation: <100ms for classification, <50ms for expansion

6. **Training Data**: Where do we get labeled queries?

   - Recommendation: Synthetic generation + manual labeling + implicit feedback

7. **Multi-Language**: Support non-English queries?
   - Recommendation: Phase 2 feature, start English-only

**Technology Stack:**

- **Classification**: Transformers library (HuggingFace) or OpenAI API
- **Expansion**: Custom dictionary + regex + embedding similarity
- **Orchestration**: Python async/await with configurable strategies
- **Storage**: Redis for query cache, SQLite for feedback data
- **Experimentation**: Simple A/B framework with statistical significance testing

**Success Criteria:**

- [ ] 90%+ query classification accuracy (human eval on 500 queries)
- [ ] 30% improvement in MRR on benchmark dataset
- [ ] 80% reduction in "no results" queries
- [ ] <100ms p95 latency overhead for query understanding
- [ ] 5+ query strategies implemented and tested

---

### EP-3: Advanced Code Graph Intelligence

**Category**: Intelligence
**Priority**: Medium
**Effort**: Large (10-14 weeks)
**Impact**: Very High

#### Vision

Unlock the full potential of the existing code graph infrastructure by building advanced graph-based analysis, visualization, and search capabilities. Enable developers to understand code relationships, dependencies, and impacts at a glance.

#### Business Value

- **Impact Analysis**: Understand change ripple effects before making edits
- **Dependency Management**: Visualize and optimize dependency structures
- **Refactoring Safety**: Identify all consumers before changing interfaces
- **Onboarding Acceleration**: New developers understand architecture 3x faster
- **Bug Prevention**: Detect architectural anti-patterns early

#### Broad Specification

**1. Enhanced Graph Extraction**

Current state: Basic node/edge extraction exists but is underutilized.

Enhancements needed:

- **Call Graph Extraction**

  - Function/method calls across files
  - Async/await flow analysis
  - Event handler relationships

- **Data Flow Tracking**

  - Variable dependencies
  - State mutations
  - Data transformations

- **Import/Dependency Graph**

  - Module-level dependencies
  - Circular dependency detection
  - Dead code identification

- **Type Relationships**

  - Inheritance hierarchies
  - Interface implementations
  - Generic type constraints

- **Cross-Language Edges**
  - Python ↔ TypeScript RPC calls
  - REST API definitions ↔ client calls
  - Database schema ↔ ORM models

**2. Graph-Powered Search**

Enhance retrieval with graph-aware ranking:

- **PageRank for Code**: Rank chunks by centrality in call graph
- **Personalized PageRank**: Rank relative to query-relevant entry points
- **Path-Based Relevance**: Prefer results on call paths from entry points
- **Community Detection**: Group related code and surface cluster summaries
- **Structural Similarity**: Find code with similar graph patterns

**3. Impact Analysis Engine**

Answer questions like:

- "If I change this function signature, what breaks?"
- "What code paths can reach this database query?"
- "Which API endpoints depend on this service?"

Implementation:

- **Forward Analysis**: Traverse call graph downstream
- **Backward Analysis**: Traverse call graph upstream
- **Transitive Closure**: Find all affected components
- **Risk Scoring**: Estimate change impact magnitude
- **Diff-Aware**: Compare graph before/after changes

**4. Visual Graph Explorer**

Interactive visualization for code exploration:

- **Web-Based UI**: D3.js or Cytoscape.js visualization
- **Filter Controls**: By language, directory, call depth, node type
- **Layout Algorithms**: Force-directed, hierarchical, circular
- **Interactive Exploration**: Click node → show neighbors, hover → show metadata
- **Export**: SVG, PNG, GraphML for documentation
- **Minimap**: Overview + detail for large graphs

**5. Architectural Insights**

Automated detection of patterns and anti-patterns:

- **Metrics**:

  - Cyclomatic complexity per function
  - Coupling between modules
  - Cohesion within modules
  - Depth of inheritance trees

- **Anti-Patterns**:

  - God classes (too many responsibilities)
  - Circular dependencies
  - Spaghetti code (high coupling, low cohesion)
  - Dead code (unreachable from entry points)

- **Best Practices**:

  - Clean layering (no violations)
  - Interface segregation
  - Dependency inversion

- **Reports**: Markdown or HTML summary with recommendations

**6. Time-Travel Code Graph**

Track graph evolution over time:

- **Historical Snapshots**: Graph state at each commit
- **Churn Analysis**: Which modules change most frequently
- **Architectural Drift**: Detect gradual degradation
- **Contributor Impact**: Visualize who affects which components
- **Hotspot Detection**: Find files with high churn + high centrality

#### Implementation Phases

**Phase 1: Graph Extraction Enhancement (4 weeks)**

- Implement call graph extraction for Python/TypeScript
- Add data flow tracking
- Store enhanced edges in graph_store
- Unit tests for extraction accuracy

**Phase 2: Graph-Powered Search (3 weeks)**

- Implement PageRank scoring
- Integrate graph features into ranking
- A/B test against baseline search
- Optimize graph query performance

**Phase 3: Impact Analysis (3 weeks)**

- Build forward/backward traversal algorithms
- Implement risk scoring
- Create CLI command: `dolphin impact <symbol>`
- VSCode extension integration

**Phase 4: Visual Explorer (4 weeks)**

- Design web UI for graph visualization
- Implement backend API for graph data
- Interactive exploration features
- Export and sharing capabilities

**Phase 5: Insights & Reports (2 weeks)**

- Implement anti-pattern detectors
- Generate architectural reports
- CI integration for quality gates

#### Technical Considerations

**Questions to Answer:**

1. **Graph Database**: Should we migrate from SQLite to Neo4j or NetworkX?

   - Recommendation: Stay SQLite for now, add optional Neo4j support for large repos

2. **Graph Storage**: How to efficiently store and query million-node graphs?

   - Recommendation: Adjacency list in SQLite + in-memory graph for hot paths

3. **Real-Time Updates**: How to incrementally update graph on file changes?

   - Recommendation: Incremental edge addition/removal, rebuild on conflicts

4. **Performance**: Can we compute PageRank on-the-fly for search?

   - Recommendation: Pre-compute PageRank on index, update incrementally

5. **Cross-Language**: How to handle Python→TypeScript calls accurately?

   - Recommendation: Pattern matching on RPC frameworks (JSON-RPC, REST annotations)

6. **Visualization Scale**: How to visualize graphs with 10K+ nodes?

   - Recommendation: Hierarchical clustering + focus+context technique

7. **Privacy**: Should graph data be included in telemetry?

   - Recommendation: Aggregate metrics only, no code structure details

8. **Integration**: Expose graph via MCP tools or REST API?
   - Recommendation: Both - MCP for agent use, REST for web UI

**Technology Stack:**

- **Graph Processing**: NetworkX (Python) for algorithms
- **Storage**: SQLite with adjacency tables (current) + optional Neo4j
- **Visualization**: React + D3.js or Cytoscape.js
- **Analysis**: Custom Python algorithms + scipy for advanced metrics
- **API**: FastAPI endpoints for graph queries
- **Export**: GraphML, DOT, JSON formats

**Success Criteria:**

- [ ] Call graph extraction for 95%+ of function calls
- [ ] Impact analysis accurate for 90%+ of symbol changes (manual verification)
- [ ] Graph-powered search improves MRR by 15%+ on dependency queries
- [ ] Visual explorer handles 5K+ node repos with <3s load time
- [ ] 10+ architectural insights detected automatically

---

### EP-4: Multi-Repository Cross-Intelligence

**Category**: Intelligence
**Priority**: Medium
**Effort**: Medium (6-8 weeks)
**Impact**: High

#### Vision

Enable Dolphin to understand relationships across multiple repositories, providing unified search, dependency tracking, and code intelligence for microservices, monorepos with submodules, and polyglot ecosystems.

#### Business Value

- **Microservices Intelligence**: Understand cross-service dependencies and APIs
- **Monorepo Support**: Navigate complex multi-project structures efficiently
- **Shared Libraries**: Track usage of internal packages across repos
- **Breaking Change Detection**: Identify consumers before changing shared APIs
- **Unified Search**: One query searches across all team repositories

#### Broad Specification

**1. Cross-Repo Dependency Tracking**

Detect and model dependencies between repositories:

- **Package Dependencies**:

  - Python: Parse `pyproject.toml`, `requirements.txt`, `setup.py`
  - TypeScript/JavaScript: Parse `package.json`, `pnpm-lock.yaml`
  - Go: Parse `go.mod`
  - Java: Parse `pom.xml`, `build.gradle`

- **API Dependencies**:

  - REST API calls: Detect fetch/axios/requests to URLs
  - RPC calls: gRPC service definitions, JSON-RPC calls
  - Message queues: Kafka topics, RabbitMQ exchanges

- **Shared Configuration**:

  - Environment variables
  - Config files (YAML, TOML, JSON)
  - Database schemas

- **Build Dependencies**:
  - Docker images
  - CI/CD pipelines
  - Shared scripts

**2. Unified Multi-Repo Search**

Enhance search to work seamlessly across repos:

- **Query Routing**: Automatically search relevant repos based on query
- **Cross-Repo Ranking**: Rank results from different repos fairly
- **Repo Affinity**: Prefer results from related repos
- **Deduplicated Results**: Handle code copied between repos
- **Repo Context**: Show which repo each result belongs to clearly

**3. Global Symbol Resolution**

Resolve symbols across repo boundaries:

- **Import Tracing**: Follow imports from one repo to another
- **API Contract Matching**: Match client calls to server definitions
- **Type Compatibility**: Check type consistency across repos
- **Version Awareness**: Handle multiple versions of shared packages

**4. Cross-Repo Impact Analysis**

Extend impact analysis across repo boundaries:

- **API Impact**: "If I change this endpoint, which client repos break?"
- **Package Impact**: "Which repos use this internal library version?"
- **Schema Impact**: "What services depend on this database table?"
- **Config Impact**: "What services use this environment variable?"

**5. Workspace Management**

Organize and manage collections of related repos:

- **Workspace Definitions**:

  ```yaml
  name: "payment-service-ecosystem"
  repos:
    - payment-api
    - payment-processor
    - shared-models
    - payment-ui
  relationships:
    - from: payment-ui
      to: payment-api
      type: rest-client
  ```

- **Workspace Operations**:
  - `dolphin workspace create <name>`
  - `dolphin workspace add-repo <workspace> <repo>`
  - `dolphin workspace search <workspace> <query>`
  - `dolphin workspace deps <workspace>` - Show dependency graph
  - `dolphin workspace sync <workspace>` - Re-index all repos

**6. Cross-Repo Visualization**

Extend visual graph explorer to show multi-repo view:

- **Repository Nodes**: Each repo as a high-level node
- **Dependency Edges**: Package and API dependencies between repos
- **Drill-Down**: Click repo → show internal structure
- **Highlight Paths**: Show call paths across repos
- **Filter by Type**: Show only API, package, or data dependencies

#### Implementation Phases

**Phase 1: Dependency Detection (2 weeks)**

- Implement package manifest parsing
- Detect API calls and match to definitions
- Store cross-repo edges in graph_store

**Phase 2: Unified Search (2 weeks)**

- Enhance search backend for multi-repo queries
- Implement fair ranking across repos
- Add repo context to UI

**Phase 3: Workspace Management (2 weeks)**

- Workspace data model and API
- CLI commands for workspace operations
- VSCode extension workspace selector

**Phase 4: Cross-Repo Analysis (2 weeks)**

- Extend impact analysis across repos
- Global symbol resolution
- Breaking change detection

#### Technical Considerations

**Questions to Answer:**

1. **Repository Registration**: How do users group related repos?

   - Recommendation: Workspace concept with YAML configuration

2. **Dependency Discovery**: Automatic vs. manual relationship definition?

   - Recommendation: Automatic with manual override capability

3. **Version Handling**: How to handle multiple versions of shared packages?

   - Recommendation: Index all versions, filter by date or explicit selection

4. **Performance**: Does indexing scale to 50+ repos?

   - Recommendation: Parallel indexing + incremental updates

5. **Access Control**: What if user doesn't have access to all repos?

   - Recommendation: Graceful degradation, show what's accessible

6. **Monorepo vs. Polyrepo**: Should these be handled differently?

   - Recommendation: Unified model, auto-detect monorepo structure

7. **Cost**: How to manage embedding costs for many repos?
   - Recommendation: Shared deduplication across repos

**Technology Stack:**

- **Dependency Parsing**: Language-specific parsers (already exist for chunking)
- **Graph Storage**: Enhanced SQLite graph_store with cross-repo edges
- **API Matching**: Pattern matching + embedding similarity
- **Workspace Config**: YAML with validation
- **UI**: Enhanced VSCode extension with workspace selector

**Success Criteria:**

- [ ] Detect 90%+ of package dependencies automatically
- [ ] Resolve 80%+ of API call sites to definitions across repos
- [ ] Multi-repo search ranks results fairly (human evaluation)
- [ ] Workspace operations work for 10+ repo workspaces
- [ ] Cross-repo impact analysis identifies all affected repos correctly

---

### EP-5: Evaluation & Quality Assurance Framework

**Category**: Intelligence
**Priority**: High
**Effort**: Medium (4-6 weeks)
**Impact**: High

#### Vision

Build a comprehensive evaluation framework that measures search quality, enables data-driven optimization, and prevents regressions. Make search quality improvements measurable and repeatable.

#### Business Value

- **Measurable Improvements**: Prove that changes improve search quality
- **Regression Prevention**: Catch quality degradations before deployment
- **Optimization Confidence**: Know which parameters to tune
- **Stakeholder Communication**: Show concrete metrics to leadership
- **Competitive Benchmarking**: Compare against other code search tools

#### Broad Specification

**1. Evaluation Datasets**

Create diverse, representative datasets:

- **Golden Query Set**:

  - 500+ queries covering all intent types
  - Manual relevance judgments (5-point scale)
  - Mix of easy/medium/hard queries
  - Diverse languages and project types

- **Synthetic Query Generation**:

  - Generate queries from code: "Find implementation of <function>"
  - Question templates: "How does X work?", "Where is X defined?"
  - Negative queries: Intentionally ambiguous or impossible queries

- **Real User Queries**:
  - Anonymized queries from VSCode extension (opt-in)
  - Click-through data for implicit relevance
  - Session context for multi-turn evaluation

**2. Evaluation Metrics**

Implement industry-standard IR metrics:

- **Ranking Quality**:

  - **MRR (Mean Reciprocal Rank)**: Position of first relevant result
  - **MAP (Mean Average Precision)**: Precision across all relevant results
  - **NDCG@K (Normalized Discounted Cumulative Gain)**: Quality at top K
  - **Precision@K**: Fraction of top K that are relevant
  - **Recall@K**: Fraction of relevant results in top K

- **Coverage**:

  - **Zero Result Rate**: Queries returning no results
  - **Result Diversity**: MMR score across result set
  - **Source Distribution**: Variety of files/modules in results

- **Efficiency**:

  - **Latency Distribution**: p50, p95, p99 search times
  - **Index Freshness**: Time from code change to searchability
  - **Cost per Query**: Embedding + search compute costs

- **User Satisfaction**:
  - **Click-Through Rate (CTR)**: Fraction of queries with clicked results
  - **Time to Success**: Time until user finds answer
  - **Reformulation Rate**: Queries requiring multiple attempts

**3. Evaluation Pipeline**

Automated evaluation infrastructure:

- **Continuous Evaluation**:

  - Run eval suite on every commit (10-minute subset)
  - Nightly full evaluation (all queries, all metrics)
  - Weekly deep evaluation (include human review)

- **A/B Testing Framework**:

  - Split traffic between baseline and experiment
  - Statistical significance testing (t-test, bootstrap)
  - Minimum sample size enforcement
  - Early stopping for clear winners/losers

- **Experiment Tracking**:
  - Log all hyperparameters and configs
  - Store results in SQLite for trending
  - Generate comparison reports (Markdown + charts)
  - Git integration: Link experiments to commits

**4. Benchmark Suite**

Compare against other code search tools:

- **Competitors**:

  - GitHub Code Search
  - Sourcegraph
  - grep/ripgrep (baseline)
  - IDE built-in search (VSCode, IntelliJ)

- **Benchmark Datasets**:

  - CodeSearchNet dataset
  - GitHub issue queries → code snippets
  - StackOverflow questions → code answers

- **Fairness**:
  - Same repos indexed by all tools
  - Same query set for all tools
  - Blind human evaluation of results

**5. Quality Dashboard**

Real-time view of search quality:

- **Grafana Dashboards**:

  - Current MRR, MAP, P@5 (updated nightly)
  - Trend lines over time
  - Per-language and per-repo breakdowns
  - Latency vs. quality trade-off curves

- **Regression Alerts**:

  - Alert if MRR drops >5% week-over-week
  - Alert if latency increases >20%
  - Alert if zero-result rate >10%

- **Leaderboard**:
  - Top 10 performing query strategies
  - Best hyperparameter configurations
  - Contributor scoreboard (who improved metrics most)

**6. Human Evaluation Interface**

Web UI for manual relevance judging:

- **Judge Workflow**:

  1. Show query and search results
  2. Judge each result: Excellent / Good / Fair / Poor / Bad
  3. Provide optional feedback text
  4. Calculate inter-annotator agreement

- **Features**:

  - Side-by-side comparison of two result sets
  - Blind evaluation (no labels shown)
  - Batch processing (judge 10 queries at once)
  - Progress tracking and quality checks

- **Recruitment**:
  - Internal team members
  - Community contributors (bounties?)
  - Synthetic judges (LLM-as-a-judge)

#### Implementation Phases

**Phase 1: Dataset Creation (2 weeks)**

- Build golden query set (manual)
- Implement synthetic query generation
- Create evaluation dataset structure

**Phase 2: Metrics & Pipeline (2 weeks)**

- Implement all IR metrics
- Build automated evaluation runner
- Integrate with CI/CD

**Phase 3: A/B Testing Framework (1 week)**

- Traffic splitting mechanism
- Statistical significance testing
- Experiment tracking database

**Phase 4: Dashboard & Alerting (1 week)**

- Grafana dashboards
- Regression alert rules
- Quality reports generation

#### Technical Considerations

**Questions to Answer:**

1. **Dataset Size**: How many queries needed for statistical significance?

   - Recommendation: Minimum 200 queries, target 500+

2. **Human Evaluation**: How many judges per query?

   - Recommendation: 3 judges for gold set, 1 for experiments

3. **Evaluation Frequency**: How often to run full eval?

   - Recommendation: Nightly for full suite, real-time for subset

4. **Regression Threshold**: What drop constitutes a regression?

   - Recommendation: >3% MRR drop or >20% latency increase

5. **Benchmark Fairness**: How to ensure fair comparison with competitors?

   - Recommendation: Identical repos, queries, and evaluation protocol

6. **LLM-as-Judge**: Should we use GPT-4 for automated evaluation?

   - Recommendation: Yes for preliminary screening, humans for final validation

7. **Public Leaderboard**: Should we publish metrics publicly?
   - Recommendation: Yes, builds credibility and attracts contributors

**Technology Stack:**

- **Evaluation Runner**: Python script with pytest integration
- **Metrics**: scikit-learn, scipy, custom implementations
- **Storage**: SQLite for results, JSON for datasets
- **Dashboard**: Grafana + Prometheus
- **A/B Framework**: Custom Python with scipy.stats
- **Human Eval UI**: Svelte web app with FastAPI backend

**Success Criteria:**

- [ ] 500+ query evaluation dataset with relevance judgments
- [ ] 10+ IR metrics computed automatically
- [ ] A/B tests run automatically on config changes
- [ ] Grafana dashboard showing quality trends
- [ ] Regression alerts trigger on >3% MRR drop
- [ ] Benchmark comparison with 3+ competitors

---

### EP-6: Performance Optimization Suite

**Category**: Foundation
**Priority**: Medium
**Effort**: Medium (5-7 weeks)
**Impact**: High

#### Vision

Systematically optimize Dolphin's performance across indexing, search, and runtime to handle large-scale enterprise workloads. Achieve 10x throughput improvements and sub-second search latency at scale.

#### Business Value

- **Scale Support**: Handle 100K+ file repos efficiently
- **Cost Reduction**: 50% reduction in embedding costs through optimization
- **User Experience**: Sub-second search response times
- **Developer Productivity**: 5x faster indexing enables rapid iteration
- **Resource Efficiency**: Run on lower-spec hardware

#### Broad Specification

**1. Indexing Pipeline Optimization**

Current bottlenecks identified in codebase analysis:

- **Parallel Processing**:

  - Current: Sequential file processing
  - Target: Parallel chunking with worker pool (8-16 workers)
  - Approach: Python multiprocessing or asyncio with process pool
  - Expected: 5-10x indexing throughput

- **Incremental Embedding**:

  - Current: Re-embed all chunks on reindex
  - Target: Only embed changed chunks (already implemented via SHA256)
  - Enhancement: Incremental vector table updates
  - Expected: 90% reduction in reindex time

- **Batch Size Optimization**:

  - Current: Fixed batch size (100 chunks)
  - Target: Adaptive batching based on text length and API latency
  - Approach: Measure throughput at various batch sizes, auto-tune
  - Expected: 30% improvement in embedding throughput

- **Tree-Sitter Caching**:
  - Current: Reparse files on every index
  - Target: Cache parsed ASTs by file hash
  - Approach: LRU cache with pickle serialization
  - Expected: 40% reduction in parsing time

**2. Search Query Optimization**

- **Query Result Caching**:

  - Implementation: Redis or in-memory LRU cache
  - Cache key: Query hash + repo filter + top_k
  - TTL: 5 minutes for exact matches, 1 hour for similar queries
  - Invalidation: On index updates for affected repos
  - Expected: 70% cache hit rate, 10x speedup for cached queries

- **Vector Search Optimization**:

  - Current: LanceDB KNN on every query
  - Enhancements:
    - Pre-filter by repo before KNN (reduces search space)
    - Adaptive nprobes based on result quality (current: fixed)
    - Parallel search across multiple repos
    - Approximate filtering with refinement
  - Expected: 40% reduction in search latency

- **Database Connection Pooling**:

  - Current: New SQLite connection per request
  - Target: Connection pool with 10-20 connections
  - Implementation: SQLAlchemy or aiosqlite
  - Expected: 30% reduction in metadata query time

- **Hybrid Search Optimization**:
  - Current: Sequential vector + BM25 queries
  - Target: Parallel execution with async
  - Implementation: asyncio.gather for vector and FTS5 queries
  - Expected: 50% reduction in hybrid search latency

**3. Storage Optimization**

- **LanceDB Compaction**:

  - Current: Append-only writes, no compaction
  - Target: Periodic compaction to reduce storage and improve query speed
  - Schedule: Weekly or after N% new data
  - Expected: 30% storage reduction, 15% query speedup

- **SQLite Optimization**:

  - WAL mode: Enable write-ahead logging for concurrency
  - PRAGMA optimize: Run after bulk operations
  - Index tuning: Analyze query plans, add missing indexes
  - VACUUM: Periodic cleanup of deleted data
  - Expected: 50% improvement in write throughput

- **Content Compression**:
  - Current: Store full chunk text in SQLite
  - Target: zstd compression for chunk_content.content
  - Trade-off: 10-20ms decompression overhead vs. 60% storage savings
  - Expected: 60% reduction in SQLite database size

**4. Runtime Performance**

- **Lazy Initialization**:

  - Current: Load embedding models on startup
  - Target: Load on first use (reduces extension activation time)
  - Implementation: Singleton with lazy loading
  - Expected: 80% reduction in API startup time

- **Webview Optimization**:

  - Code splitting: Load features on demand
  - Virtual scrolling: Render only visible messages
  - Debounced search: Wait 300ms before searching
  - Memoization: Cache rendered components
  - Expected: 3x improvement in webview responsiveness

- **Agent Core IPC**:
  - Current: JSON serialization per message
  - Target: MessagePack binary serialization
  - Implementation: Replace JSON.stringify/parse
  - Expected: 40% reduction in IPC overhead

**5. Profiling & Monitoring**

- **Continuous Profiling**:

  - Python: cProfile or py-spy sampling profiler
  - TypeScript: Chrome DevTools profiler or clinic.js
  - Visualization: Flame graphs for hotspot identification
  - Integration: Run profiling in CI on performance benchmarks

- **Performance Budgets**:
  - Indexing: <10 min for 10K file repo
  - Search: <300ms p50, <1s p95
  - Extension activation: <2s
  - Webview load: <1s
  - CI enforcement: Fail build if budgets exceeded

**6. Load Testing**

- **Scenarios**:

  - Concurrent search: 10 simultaneous users
  - Indexing during search: Simulate background indexing
  - Large result sets: Queries returning 100+ results
  - Stress test: 100 QPS for 5 minutes

- **Tools**:

  - Locust or k6 for HTTP load testing
  - Custom scripts for CLI operations
  - Monitoring: Track latency, error rate, resource usage

- **Automation**:
  - Weekly load tests in CI
  - Nightly performance regression tests
  - Compare against previous version baseline

#### Implementation Phases

**Phase 1: Profiling & Baseline (1 week)**

- Profile indexing and search pipelines
- Identify top 10 bottlenecks
- Establish performance baselines

**Phase 2: Indexing Optimization (2 weeks)**

- Implement parallel processing
- Optimize batch sizes
- Add tree-sitter caching

**Phase 3: Search Optimization (2 weeks)**

- Implement query caching
- Optimize vector search
- Add connection pooling

**Phase 4: Storage & Runtime (1 week)**

- LanceDB compaction
- SQLite optimization
- Webview improvements

**Phase 5: Load Testing (1 week)**

- Build load test suite
- Run comprehensive tests
- Generate performance report

#### Technical Considerations

**Questions to Answer:**

1. **Parallel vs. Async**: Multiprocessing or asyncio for indexing?

   - Recommendation: Multiprocessing for CPU-bound parsing/hashing, asyncio for I/O-bound embedding

2. **Cache Strategy**: Redis vs. in-memory?

   - Recommendation: In-memory for single-user, Redis for multi-user deployments

3. **LanceDB vs. Alternatives**: Is LanceDB the bottleneck?

   - Recommendation: Profile first, consider Faiss/Annoy if LanceDB is limiting factor

4. **Compression Trade-off**: Is 10ms decompression acceptable?

   - Recommendation: Make it configurable, benchmark on target hardware

5. **Performance Budgets**: Are these targets realistic?

   - Recommendation: Based on current 2x slower performance, budgets are achievable

6. **Breaking Changes**: Will optimizations require API changes?

   - Recommendation: Maintain backward compatibility, make optimizations opt-in initially

7. **Measurement Overhead**: How much does profiling slow things down?
   - Recommendation: Use sampling profilers (1-5% overhead) for production

**Technology Stack:**

- **Profiling**: py-spy (Python), clinic.js (Node/Bun)
- **Caching**: Redis (distributed) or functools.lru_cache (local)
- **Async**: asyncio (Python), native async/await (TypeScript)
- **Compression**: zstd (fast, high ratio)
- **Load Testing**: Locust (Python) or k6 (Go)
- **Visualization**: Flame graphs (speedscope.app)

**Success Criteria:**

- [ ] Indexing throughput: 5x improvement (500 → 2500 files/min)
- [ ] Search latency: 50% reduction (300ms → 150ms p50)
- [ ] Cache hit rate: 70%+ on repeated queries
- [ ] Extension activation: <2s (down from 5s)
- [ ] Storage: 50% reduction in database size with compression
- [ ] Load test: Sustain 20 QPS with <1s p95 latency

---

### EP-7: Enhanced Developer Experience

**Category**: Experience
**Priority**: High
**Effort**: Medium (6-8 weeks)
**Impact**: High

#### Vision

Create a delightful, intuitive developer experience that makes Dolphin the fastest and most enjoyable way to understand and navigate codebases. Reduce friction, add automation, and provide intelligent assistance at every step.

#### Business Value

- **Adoption**: 3x increase in user onboarding completion
- **Engagement**: 5x increase in daily active usage
- **Satisfaction**: NPS score >70
- **Productivity**: Developers answer questions 10x faster
- **Retention**: Reduce churn by 60%

#### Broad Specification

**1. Zero-Config Onboarding**

Current pain points: Multi-step setup, manual KB server management.

**Improvements:**

- **Automatic Detection**:

  - Detect `.dolphin/config.toml` on workspace open
  - Prompt: "This workspace has Dolphin configured. Index now?"
  - Auto-detect programming languages and suggest optimal settings

- **Setup Wizard**:

  - Step 1: Welcome and feature overview (30-second video)
  - Step 2: API key setup (auto-detect from env, offer to save securely)
  - Step 3: Select repos to index (auto-detect git repos in workspace)
  - Step 4: Indexing preferences (speed vs. quality slider)
  - Step 5: Start indexing (progress indicator, time estimate)

- **Smart Defaults**:

  - Auto-configure chunking based on repo size and languages
  - Set reasonable `top_k` and `score_cutoff` based on repo characteristics
  - Enable/disable expensive features (reranking) based on hardware

- **Background Indexing**:
  - Index in background with <10% CPU usage
  - Debounce file saves
  - Resume on idle or schedule for off-hours

**2. Intelligent Code Navigation**

Enhance VSCode extension with smart navigation features:

- **Related Files**:

  - Sidebar panel showing semantically related files
  - Auto-update as you navigate code
  - Include tests, imports, and implementers

- **Contextual Commands**:

  - Right-click symbol → "Ask about this function"
  - Right-click file → "Summarize this file"
  - Right-click folder → "Explain this module"
  - Selection → "Find similar code patterns"

- **Breadcrumb Trail** (Descoped):

  - Show call path from entry point to current function
  - Click any breadcrumb to jump to that level
  - Visualize as hierarchical tree in sidebar

**3. Conversational AI Enhancements**

Improve the chat interface with better AI interactions:

- **Quick Actions**:

  - Pre-defined functions/personas (e.g., Code Review, Plan Project, Journalist/Documentarian)
  - Customizable quick action buttons
  - Keyboard shortcuts for common actions

- **Multi-File Operations**:

  - "Explain how authentication works" → Automatically searches and synthesizes answer from multiple files
  - "Refactor error handling" → Suggests changes across multiple files
  - "Update all API calls to v2" → Batch editing with preview

**5. Collaboration Features**

Enable team knowledge sharing:

- **Code Annotations**:

  - Add notes to specific code locations
  - Visible to all team members
  - Markdown support with screenshots
  - Link to Jira/GitHub issues

- **Shared Queries**:

  - Save and share useful queries with team
  - "How to deploy", "Where is config?", "Common errors"
  - Query library with categorization

- **Team Insights**:

  - Dashboard showing what code teammates are exploring
  - Hot files: What's being viewed most
  - Knowledge gaps: Areas with few annotations or questions

- **Review Mode**:
  - Code review checklist generator
  - AI-suggested review comments
  - Integration with GitHub PR reviews

**6. CLI & Automation Improvements**

Enhance CLI experience:

- **Interactive Mode**:

  - `dolphin` (no args) starts interactive REPL
  - Tab completion for commands and repos
  - Colorized output with syntax highlighting

- **Doctor Command**:

  - `dolphin doctor` diagnoses common issues
  - Checks: API key, disk space, port conflicts, dependencies
  - Suggests fixes for detected problems
  - Validates configuration files

- **Watch Mode**:

  - `dolphin watch <repo>` auto-reindexes on file changes
  - Smart debouncing: Wait for editing to stop
  - Incremental updates only

- **Pre-commit Hook**:

  - Enable CLI install of git hook to index on commit (check if index is up to date before install)
  - Runs `dolphin index --incremental` in background
  - Skip if commit is urgent (`--no-verify` flag)

- **Shell Completion**:
  - Bash, Zsh, Fish completion scripts
  - Complete repo names, file paths, config keys
  - `dolphin search <tab>` shows recent queries

**7. UI/UX Polish**

Visual and interaction improvements:

- **Themes**:

  - Light, dark, and high-contrast themes
  - Sync with VSCode theme automatically
  - Custom theme editor

- **Accessibility**:

  - Full keyboard navigation
  - Screen reader support (ARIA labels)
  - High-contrast mode
  - Adjustable font sizes

- **Animations**:

  - Smooth transitions between views
  - Loading skeletons instead of spinners
  - Subtle micro-interactions (hover effects, focus states)

- **Responsive Design**:
  - Adapt layout to webview size

#### Implementation Phases

**Phase 1: Onboarding (2 weeks)**

- Setup wizard UI
- Auto-detection logic
- Background indexing

**Phase 2: Navigation (2 weeks)**

- Enhanced definition jumps
- Related files sidebar
- Breadcrumb trail

**Phase 3: AI Enhancements (2 weeks)**

- Quick actions
- Multi-file operations
- Inline suggestions

**Phase 4: Collaboration (2 weeks)**

- Code annotations
- Shared queries
- Team insights

#### Technical Considerations

**Questions to Answer:**

1. **Setup Complexity**: What's acceptable onboarding time?

   - Target: <3 minutes from install to first search

2. **Background Indexing**: How to balance speed vs. resource usage?

   - Recommendation: Adaptive throttling based on CPU/memory pressure

3. **Voice Input**: Is this a gimmick or valuable feature?

   - Recommendation: Start with opt-in experimental feature, gather feedback

4. **Collaboration Storage**: Where to store team annotations?

   - Recommendation: Local `.dolphin/annotations.json` in git repo (team-shared)

5. **Privacy**: How to handle team insights without invading privacy?

   - Recommendation: Aggregate only, opt-in, no individual tracking

6. **Accessibility**: What WCAG level to target?

   - Recommendation: WCAG 2.1 AA compliance

7. **Offline Support**: Should Dolphin work without internet?
   - Recommendation: Yes for search (local), no for embedding (requires API)

**Technology Stack:**

- **UI**: Svelte 5 with SvelteKit, Tailwind CSS, shadcn/ui
- **Diagrams**: Mermaid.js, D3.js
- **Accessibility**: radix-ui primitives, ARIA attributes
- **CLI**: Typer (Python), Inquirer for interactive prompts
- **Storage**: Local JSON/TOML files for annotations

**Success Criteria:**

- [ ] Setup wizard completion rate >80%
- [ ] Onboarding time: <3 minutes from install to first search
- [ ] Enhanced navigation used in 50%+ of sessions
- [ ] Quick actions account for 30%+ of queries
- [ ] Documentation generation accuracy >70% (human evaluation)
- [ ] WCAG 2.1 AA accessibility compliance

---

### EP-8: Enterprise-Grade Security & Compliance

**Category**: Enterprise
**Priority**: Medium
**Effort**: Large (8-12 weeks)
**Impact**: Very High (for enterprise adoption)

#### Vision

Transform Dolphin into an enterprise-ready platform with robust security controls, compliance features, and auditability. Enable adoption by security-conscious organizations with strict governance requirements.

#### Business Value

- **Enterprise Sales**: Unlock $100K+ contracts with large organizations
- **Risk Mitigation**: Reduce security incidents by 95%
- **Compliance**: Enable usage in regulated industries (finance, healthcare, government)
- **Trust**: Build confidence with security-conscious buyers
- **Competitive Advantage**: Differentiate from open-source alternatives

#### Broad Specification

**1. Authentication & Authorization**

Current state: Single-user, local access only.

**Enterprise Requirements:**

- **Multi-User Authentication**:

  - Local accounts with bcrypt password hashing
  - SSO integration (SAML 2.0, OAuth 2.0, OIDC)
  - API key authentication for programmatic access
  - Service account support for CI/CD

- **Role-Based Access Control (RBAC)**:

  - Roles: Admin, Developer, Read-Only, Auditor
  - Permissions: Index, Search, Configure, Audit
  - Repo-level permissions: Access control per repository
  - Fine-grained: Control access to specific features

- **Multi-Tenancy**:

  - Logical isolation: Each team has separate namespace
  - Resource quotas: Index size, query rate, storage limits
  - Cost tracking: Attribute embedding costs to teams

- **Session Management**:
  - JWT-based sessions with expiry
  - Refresh token rotation
  - Concurrent session limits
  - Force logout on password change

**2. Data Security**

Protect sensitive code and data:

- **Encryption at Rest**:

  - SQLite database encryption (SQLCipher)
  - LanceDB encryption (AES-256)
  - Encrypted backups
  - Key management (KMS integration: AWS KMS, HashiCorp Vault)

- **Encryption in Transit**:

  - TLS 1.3 for all HTTP connections
  - Certificate pinning for API clients
  - Mutual TLS (mTLS) for service-to-service communication

- **Secrets Management**:

  - Never log secrets (auto-redaction)
  - Secure storage of API keys (OS keychain or Vault)
  - Rotation policy enforcement (90-day expiry)
  - Secret scanning: Detect accidentally committed secrets

- **Data Retention**:
  - Configurable retention policies (delete after N days)
  - Secure deletion (wipe, not just unlink)
  - Backup encryption and access controls
  - GDPR right-to-be-forgotten compliance

**3. Audit Logging**

Comprehensive audit trail:

- **Audit Events**:

  - Authentication: Login, logout, failed attempts, password changes
  - Authorization: Permission grants/revokes, role changes
  - Data access: Search queries, file fetches, chunk access
  - Configuration: Index operations, repo additions, setting changes
  - Admin actions: User creation, permission changes, system config

- **Audit Log Format**:

  ```json
  {
    "timestamp": "2025-11-11T10:30:00Z",
    "event_type": "search",
    "user_id": "user@example.com",
    "user_ip": "192.168.1.100",
    "repo": "payment-service",
    "query": "[REDACTED]",
    "results_count": 8,
    "status": "success",
    "correlation_id": "abc123"
  }
  ```

- **Audit Log Storage**:

  - Append-only log file with rotation
  - Immutable storage (S3 with object lock, WORM drives)
  - Tamper-evident (cryptographic checksums)
  - Long-term retention (7 years for compliance)

- **Audit Reporting**:
  - Search audit logs by user, date, event type
  - Generate compliance reports (SOC 2, HIPAA, GDPR)
  - Anomaly detection: Unusual access patterns, bulk downloads
  - Integration with SIEM (Splunk, ELK, Datadog)

**4. Secrets Detection & Prevention**

Prevent accidental exposure of credentials:

- **Pre-Index Scanning**:

  - Scan files before indexing for secrets
  - Patterns: API keys, passwords, private keys, tokens
  - Entropy detection: High-entropy strings (likely secrets)
  - Machine learning: Trained model for secret detection

- **Blocklist**:

  - Automatically exclude files with detected secrets
  - Warn user and suggest adding to `.gitignore`
  - Quarantine mode: Index without embedding sensitive parts

- **Post-Index Monitoring**:

  - Periodic rescanning of indexed content
  - Alert on newly detected secrets (keys leaked in commit)
  - Automated remediation: Remove from index, notify user

- **Search Result Filtering**:
  - Redact secrets in search results
  - Mask API keys: `sk-...abcd` (show first/last 4 chars)
  - Warning banner if results contain secrets

**5. Compliance & Certifications**

Work toward industry compliance:

- **SOC 2 Type II**:

  - Security: Access controls, encryption, monitoring
  - Availability: Uptime monitoring, incident response
  - Processing Integrity: Input validation, error handling
  - Confidentiality: Data protection, access logs
  - Privacy: Data handling, retention policies

- **GDPR Compliance**:

  - Data minimization: Only index necessary code
  - Right to access: Export user's queries and annotations
  - Right to erasure: Delete user data on request
  - Data portability: Export in machine-readable format
  - Privacy by design: Minimize data collection

- **HIPAA** (if applicable):

  - PHI protection: Never index patient data
  - Access controls: Audit all PHI access
  - Encryption: At rest and in transit
  - BAA agreements: With cloud providers

- **ISO 27001**:
  - ISMS (Information Security Management System)
  - Risk assessment and treatment
  - Security policies and procedures
  - Regular audits and reviews

**6. Network Security**

Harden network attack surface:

- **API Security**:

  - Rate limiting: 100 req/min per user, 1000 req/min global
  - DDoS protection: Cloudflare or AWS Shield
  - Input validation: Strict schemas, reject invalid requests
  - CORS: Whitelist allowed origins
  - CSRF protection: Tokens for state-changing operations

- **Firewall Rules**:

  - Restrict KB API to localhost by default
  - Production: Whitelist IPs or use VPN
  - Block all except necessary ports

- **Dependency Security**:
  - Automated vulnerability scanning (Snyk, Dependabot)
  - Pin dependencies to specific versions
  - Regular updates for security patches
  - Supply chain verification (SBOM, signed packages)

**7. Penetration Testing & Security Reviews**

Ongoing security validation:

- **Internal Pen Testing**:

  - Quarterly security reviews by team
  - OWASP Top 10 testing
  - Automated security scanners (Burp Suite, OWASP ZAP)

- **External Audits**:

  - Annual third-party penetration test
  - Bug bounty program (HackerOne, Bugcrowd)
  - Security researcher engagement

- **Code Security**:
  - Static analysis: Bandit (Python), ESLint security plugin (TS)
  - Dependency scanning: Snyk, npm audit, pip-audit
  - Secret scanning: TruffleHog, git-secrets
  - Pre-commit hooks for security checks

#### Implementation Phases

**Phase 1: Authentication & RBAC (3 weeks)**

- Implement user accounts and authentication
- Build RBAC system with roles and permissions
- Multi-tenancy data model

**Phase 2: Encryption & Secrets (3 weeks)**

- Database encryption
- TLS enforcement
- Secrets detection and prevention

**Phase 3: Audit Logging (2 weeks)**

- Implement comprehensive audit logging
- Build audit log search and reporting
- SIEM integration

**Phase 4: Compliance (3 weeks)**

- GDPR compliance implementation
- SOC 2 controls documentation
- Privacy policy and terms

**Phase 5: Security Hardening (1 week)**

- Rate limiting and DDoS protection
- Penetration testing
- Security documentation

#### Technical Considerations

**Questions to Answer:**

1. **Authentication Backend**: Build in-house or use existing (Auth0, Keycloak)?

   - Recommendation: Keycloak for self-hosted, Auth0 for SaaS

2. **Encryption Performance**: How much does SQLCipher slow down queries?

   - Recommendation: Benchmark, expect 10-20% overhead, acceptable for security

3. **Multi-Tenancy**: Logical vs. physical isolation?

   - Recommendation: Logical (shared DB with tenant_id) for cost, physical for highest security

4. **Secrets Detection**: False positive rate tolerance?

   - Recommendation: Aggressive detection with manual override capability

5. **Audit Log Size**: How to manage log growth?

   - Recommendation: Compress and archive after 90 days, delete after 7 years

6. **Compliance Scope**: Full SOC 2 or just security controls?

   - Recommendation: Start with security controls, expand to full SOC 2 for enterprise sales

7. **Open Source**: Can security features remain open source?
   - Recommendation: Yes, security through transparency, not obscurity

**Technology Stack:**

- **Authentication**: Keycloak (self-hosted) or Auth0 (SaaS)
- **Encryption**: SQLCipher (SQLite), AES-256-GCM (LanceDB)
- **Secrets**: TruffleHog, git-secrets, custom ML model
- **Audit**: Structured logs to stdout, aggregated by Loki/ELK
- **SIEM**: Splunk, ELK, or Datadog
- **Security Scanning**: Snyk, Bandit, ESLint security, OWASP ZAP

**Success Criteria:**

- [ ] Multi-user authentication with SSO support
- [ ] RBAC with 4+ roles and repo-level permissions
- [ ] All data encrypted at rest (SQLite, LanceDB)
- [ ] Comprehensive audit logging with SIEM integration
- [ ] Secrets detection with <5% false positive rate
- [ ] Pass external penetration test with no critical findings
- [ ] SOC 2 Type II audit ready (if pursuing certification)

---

### EP-9: Web-Based Knowledge Portal

**Category**: Experience
**Priority**: Low
**Effort**: Large (10-14 weeks)
**Impact**: High (for non-VSCode users)

#### Vision

Build a standalone web application that provides a beautiful, powerful code search and exploration experience accessible from any browser. Enable teams without VSCode to benefit from Dolphin's intelligence.

#### Business Value

- **Broader Adoption**: Support teams using other editors (IntelliJ, Vim, etc.)
- **Management Access**: Non-technical stakeholders can explore code
- **Documentation Hub**: Centralized knowledge base for entire organization
- **Mobile Access**: Search code from phone/tablet
- **Customer Support**: Support engineers can search codebase to answer questions

#### Broad Specification

**1. Core Search Interface**

Beautiful, fast search experience:

- **Search Box**:

  - Large, prominent search box on landing page
  - Auto-complete suggestions as you type
  - Recent searches dropdown
  - Advanced search link (filters, options)

- **Results Page**:

  - List view with code snippets
  - Highlighting of matched terms
  - File path breadcrumbs (clickable)
  - Result metadata: Language, last modified, symbol type
  - Pagination or infinite scroll
  - Export results (CSV, JSON, Markdown)

- **Filters & Facets**:
  - Repository filter (multi-select)
  - Language filter
  - Path prefix filter
  - Date range (last modified)
  - Symbol type (function, class, variable)
  - File size range

**2. Code Viewer**

Rich code browsing experience:

- **Syntax Highlighting**:

  - Support 50+ languages via Prism or Monaco
  - Theme selection (light/dark/high-contrast)
  - Line numbers and gutter

- **Navigation**:

  - Jump to definition (if indexed)
  - Find references (cross-file)
  - Symbol outline (sidebar)
  - Breadcrumb navigation

- **Annotations**:

  - Inline comments and discussions
  - Link to related docs or issues
  - Code review comments

- **Actions**:
  - Copy code snippet
  - Download file
  - Open in editor (VSCode deep link, IntelliJ link)
  - Share link (permalink to specific line)

**3. Repository Browser**

Explore repository structure:

- **File Tree**:

  - Collapsible directory tree
  - Search within tree
  - File icons by type
  - Size and last modified metadata

- **Repository Dashboard**:

  - Overview: Description, languages, contributors
  - Statistics: Files, lines, chunks, index size
  - Recent commits and changes
  - Index health: Last indexed, errors, warnings

- **Batch Operations**:
  - Bulk re-index selected repos
  - Export repository metadata
  - Compare two repositories

**4. Knowledge Hub Features**

Organizational knowledge management:

- **Documentation Pages**:

  - Markdown wiki pages
  - Link to code locations
  - Embed search results dynamically
  - Version control (git-backed storage)

- **Saved Searches**:

  - Create and save useful queries
  - Share with team via link
  - Schedule: Run query daily, email results

- **Dashboards**:

  - Custom dashboards with widgets
  - Widgets: Recent changes, top files, code metrics, team activity
  - Embeddable in other tools (iframe)

- **Learning Paths**:
  - Curated tours through codebase
  - "Start here if you're new to the payment service"
  - Step-by-step guides with code references

**5. Collaborative Features**

Team collaboration tools:

- **Code Annotations**:

  - Add notes to specific lines or files
  - Mention teammates (@username)
  - Attach screenshots or links
  - Threaded discussions

- **Collections**:

  - Bookmark files or code snippets
  - Organize into collections (like playlists)
  - Share collections with team
  - Export as documentation

- **Activity Feed**:
  - See what teammates are exploring
  - Recent annotations and discussions
  - Index updates and new repos
  - Opt-in feature (privacy controls)

**6. AI Assistant Integration**

Bring Agent Core to the web:

- **Chat Interface**:

  - Same conversational AI as VSCode extension
  - Streaming responses
  - Tool call visualization

- **Contextual Questions**:

  - Right-click code → "Explain this"
  - "How is this function used?"
  - "What does this file do?"

- **Code Generation**:
  - Generate tests, docs, examples
  - Refactoring suggestions
  - Code review automation

**7. Admin Portal**

Management and configuration:

- **User Management**:

  - List users, roles, permissions
  - Add/remove users
  - Reset passwords, manage API keys

- **Repository Management**:

  - Add/remove repos
  - Configure indexing schedules
  - View index status and logs

- **System Health**:

  - Metrics dashboard (queries, latency, errors)
  - Logs viewer and search
  - Alerts and notifications

- **Settings**:
  - Configure embedding provider
  - Set system-wide defaults
  - Branding: Logo, colors, custom domain

#### Implementation Phases

**Phase 1: Core Search (4 weeks)**

- Build search interface and results page
- Implement code viewer with syntax highlighting
- Basic filtering and pagination

**Phase 2: Repository Browser (2 weeks)**

- File tree navigation
- Repository dashboard
- Batch operations

**Phase 3: Knowledge Hub (3 weeks)**

- Documentation pages
- Saved searches
- Custom dashboards

**Phase 4: Collaboration (3 weeks)**

- Code annotations
- Collections
- Activity feed

**Phase 5: AI Integration (2 weeks)**

- Chat interface
- Contextual questions
- Code generation

#### Technical Considerations

**Questions to Answer:**

1. **Frontend Framework**: React, Vue, or Svelte?

   - Recommendation: SvelteKit (consistency with VSCode extension webview)

2. **Authentication**: Reuse agent-core auth or separate?

   - Recommendation: Shared authentication service (Keycloak)

3. **Real-Time Updates**: WebSockets or polling for live activity feed?

   - Recommendation: Server-Sent Events (SSE) for simplicity

4. **Deployment**: Standalone app or embedded in KB API?

   - Recommendation: Standalone Next.js/SvelteKit app, proxied through KB API

5. **Mobile Experience**: Responsive or separate mobile app?

   - Recommendation: Responsive web app, evaluate native app later

6. **Offline Support**: Progressive Web App (PWA)?

   - Recommendation: Yes, cache search results and viewed files

7. **Branding**: White-label support for enterprise customers?
   - Recommendation: Yes, custom logo, colors, domain (enterprise feature)

**Technology Stack:**

- **Frontend**: SvelteKit with TypeScript
- **UI**: Tailwind CSS, shadcn/ui, Radix UI
- **Code Viewer**: Monaco Editor (VSCode engine) or Prism
- **State**: Svelte stores, optional Zustand for complex state
- **API**: REST client to KB API, same as extension
- **Real-Time**: Server-Sent Events (SSE)
- **Deployment**: Docker container, Kubernetes-ready

**Success Criteria:**

- [ ] Search latency: <500ms p95 (including network)
- [ ] Code viewer supports 50+ languages with syntax highlighting
- [ ] Mobile-responsive with usable experience on phone
- [ ] AI chat achieves 80% feature parity with VSCode extension
- [ ] 90%+ uptime SLA
- [ ] Lighthouse score >90 (performance, accessibility, SEO)

---

### EP-10: Collaborative Features & Team Intelligence

**Category**: Experience
**Priority**: Low
**Effort**: Medium (6-8 weeks)
**Impact**: Medium-High

#### Vision

Transform Dolphin from a single-user tool into a team collaboration platform. Enable knowledge sharing, collective intelligence, and collaborative code exploration across development teams.

#### Business Value

- **Knowledge Retention**: Capture tribal knowledge before people leave
- **Onboarding**: New hires get up to speed 5x faster
- **Team Alignment**: Shared understanding of codebase reduces miscommunication
- **Quality**: Collective code review and annotations improve quality
- **Productivity**: Team members don't re-discover the same information

#### Broad Specification

**1. Shared Annotations**

Collaborative code commenting:

- **Annotation Types**:

  - **Note**: General observation or explanation
  - **Question**: Ask teammates for clarification
  - **Warning**: Highlight potential issues or gotchas
  - **TODO**: Track technical debt or future improvements
  - **Link**: Reference external docs, tickets, or PRs

- **Annotation Features**:

  - Attach to specific lines, ranges, or entire files
  - Markdown formatting with code blocks
  - Mention teammates (@username for notifications)
  - Attach screenshots or images
  - Categorize with tags (#bug, #architecture, #performance)

- **Storage**:
  - Stored in `.dolphin/annotations/` directory in repo
  - JSON format with versioning
  - Git-committable (team shares via version control)
  - Optional: Central server for cross-repo annotations

**2. Team Knowledge Graph**

Capture collective understanding:

- **Knowledge Nodes**:

  - **Concepts**: High-level ideas (e.g., "authentication flow")
  - **Components**: Modules, services, libraries
  - **Patterns**: Design patterns used in codebase
  - **Decisions**: ADRs (Architecture Decision Records)

- **Relationships**:

  - "Concept X is implemented in Component Y"
  - "Pattern P solves Problem Q"
  - "Decision D affects Components A, B, C"

- **Knowledge Cards**:

  - Title, description, related code locations
  - Contributors and last updated
  - Tags and categories
  - Linked resources (docs, diagrams, videos)

- **Discovery**:
  - Search knowledge graph alongside code
  - "How does authentication work?" → Concept card + code references
  - Auto-suggest related concepts while browsing code

**3. Team Insights Dashboard**

Visualize team activity and knowledge:

- **Activity Metrics**:

  - Who's exploring what code (opt-in, privacy-respecting)
  - Hot files: Most viewed/searched
  - Knowledge gaps: Code with few annotations or searches
  - Collaboration heatmap: Which team members work in which areas

- **Expertise Mapping**:

  - Automatically infer expertise from activity
  - "Who knows about the payment processing module?"
  - Show top contributors to each area
  - Suggest reviewers based on expertise

- **Code Health Indicators**:
  - Annotation density (well-documented vs. mysterious)
  - Question resolution rate (unanswered questions)
  - Churn vs. annotations (high churn + low docs = risk)
  - Orphaned code (no recent viewers or editors)

**4. Collaborative Search**

Team-enhanced search experience:

- **Query Sharing**:

  - "Share this search" button copies link
  - Saved searches visible to team
  - Search templates: Fill in the blanks

- **Collective Ranking**:

  - Upvote/downvote search results
  - Personalized ranking based on team feedback
  - "Top result for 8/10 team members"

- **Query Suggestions**:
  - Learn from team's searches
  - "Others also searched for..."
  - Auto-complete from team's query history

**5. Code Tours**

Guided walkthroughs of codebase:

- **Tour Structure**:

  - Series of steps, each highlighting code + explanation
  - Step: File path, line range, description, next action
  - Branching paths: "If you're interested in X, go to step 5, otherwise 6"

- **Use Cases**:

  - Onboarding: "New engineer orientation"
  - Feature tours: "How search indexing works"
  - Bug investigation: "Tracing the authentication bug"
  - Refactoring: "What we changed and why"

- **Creation**:

  - Record mode: Create tour as you navigate
  - Manual mode: Write steps explicitly
  - Collaborative editing: Team can improve tours

- **Playback**:
  - Step-by-step navigation in VSCode or web portal
  - Automatic file opening and scrolling
  - Progress tracking and bookmarking

**6. Team Chat & Discussions**

Contextual conversations:

- **Threaded Discussions**:

  - Start discussion on any file or code snippet
  - Threaded replies
  - Resolved/unresolved status
  - Link to issues or PRs

- **Real-Time Chat**:

  - Ephemeral chat channel per repo or team
  - Code snippet sharing in chat
  - Screen sharing integration

- **Q&A Forum**:
  - Stack Overflow-style Q&A
  - Questions auto-linked to relevant code
  - Best answer voting
  - AI-suggested answers from docs and code

**7. Collective Code Review**

Team-wide review insights:

- **Review Checklist Templates**:

  - Security checklist: "Check for SQL injection, XSS, etc."
  - Performance: "Are there N+1 queries? Unnecessary loops?"
  - Style: "Follows team conventions?"

- **Review Insights**:

  - Common issues: What gets flagged most
  - Reviewer effectiveness: Who catches most bugs
  - Review coverage: What code is rarely reviewed

- **AI-Assisted Review**:
  - Auto-detect issues from checklist
  - Suggest reviewers based on expertise
  - Summarize changes for reviewers

#### Implementation Phases

**Phase 1: Shared Annotations (2 weeks)**

- Implement annotation data model
- VSCode extension UI for creating/viewing annotations
- Git-based storage

**Phase 2: Team Knowledge Graph (3 weeks)**

- Knowledge node data model
- Knowledge card UI
- Search integration

**Phase 3: Team Insights (2 weeks)**

- Activity tracking (opt-in)
- Insights dashboard
- Expertise mapping

**Phase 4: Code Tours (3 weeks)**

- Tour data format
- Record and playback functionality
- Tour editor UI

#### Technical Considerations

**Questions to Answer:**

1. **Privacy**: How much team activity tracking is acceptable?

   - Recommendation: Opt-in, aggregate only, no individual monitoring

2. **Storage**: Git-based (distributed) vs. server-based (centralized)?

   - Recommendation: Git-based for small teams, server for large teams

3. **Real-Time**: How to sync annotations across teammates?

   - Recommendation: Git commits for durability, WebSockets for real-time preview

4. **Access Control**: Can annotations be private?

   - Recommendation: Yes, personal vs. team annotations

5. **Notification Overload**: How to avoid spamming teammates?

   - Recommendation: Smart notifications, digest mode, user preferences

6. **Expertise**: How to avoid "expert shaming" (you should know this)?

   - Recommendation: Emphasize learning, not judgment. "Top contributors" not "experts"

7. **Moderation**: What if annotations are inappropriate?
   - Recommendation: Report/flag mechanism, team admin can remove

**Technology Stack:**

- **Annotations**: JSON files in `.dolphin/annotations/`
- **Real-Time**: WebSockets (Socket.io) or Server-Sent Events
- **Knowledge Graph**: SQLite with graph edges, NetworkX for queries
- **Chat**: Matrix protocol or custom WebSocket chat
- **Tours**: JSON format, playback engine in extension

**Success Criteria:**

- [ ] Annotation creation and viewing in <5 seconds
- [ ] Knowledge graph contains 100+ nodes after 1 month of use
- [ ] Team insights dashboard shows 10+ metrics
- [ ] Code tours reduce onboarding time by 50% (survey)
- [ ] 80% of team uses annotations regularly (weekly active)
- [ ] Expertise mapping accuracy >70% (team validation)

---

## Prioritization Matrix

Projects ranked by Priority, Effort, and Impact:

| Project                    | Priority | Effort | Impact      | Score | Rec. Order |
| -------------------------- | -------- | ------ | ----------- | ----- | ---------- |
| EP-1: Observability        | High     | Medium | High        | 9     | 1          |
| EP-2: Query Understanding  | High     | Large  | Very High   | 10    | 2          |
| EP-5: Evaluation Framework | High     | Medium | High        | 9     | 3          |
| EP-7: Developer Experience | High     | Medium | High        | 9     | 4          |
| EP-3: Code Graph           | Medium   | Large  | Very High   | 8     | 5          |
| EP-6: Performance          | Medium   | Medium | High        | 7     | 6          |
| EP-4: Multi-Repo           | Medium   | Medium | High        | 7     | 7          |
| EP-8: Security             | Medium   | Large  | Very High\* | 9\*   | 8          |
| EP-9: Web Portal           | Low      | Large  | High\*\*    | 6     | 9          |
| EP-10: Collaboration       | Low      | Medium | Medium-High | 5     | 10         |

**Notes:**

- \*EP-8 Impact is "Very High" specifically for enterprise adoption, but "Low" for open-source/single-user scenarios
- \*\*EP-9 Impact is "High" for teams not using VSCode, but "Low" if all users have VSCode

**Scoring**: Priority (1-3) × Impact (1-4) × (1 / Effort (1-3))

---

## Implementation Roadmap

### Year 1: Foundation & Intelligence

**Q1 2026 (Weeks 1-13)**

- **EP-1: Observability** (Weeks 1-6)

  - Core metrics and distributed tracing
  - Grafana dashboards
  - Alerting infrastructure

- **EP-5: Evaluation Framework** (Weeks 7-12)
  - Golden dataset creation
  - Metrics implementation
  - A/B testing framework

**Q2 2026 (Weeks 14-26)**

- **EP-2: Query Understanding** (Weeks 14-25)

  - Query classification
  - Query expansion
  - Multi-stage retrieval
  - Feedback loop

- **EP-7: Developer Experience (Part 1)** (Weeks 26-30)
  - Zero-config onboarding
  - Setup wizard

**Q3 2026 (Weeks 27-39)**

- **EP-6: Performance Optimization** (Weeks 31-37)

  - Profiling and baseline
  - Indexing optimization
  - Search optimization
  - Load testing

- **EP-7: Developer Experience (Part 2)** (Weeks 38-43)
  - Intelligent navigation
  - Conversational AI enhancements
  - Documentation generation

**Q4 2026 (Weeks 40-52)**

- **EP-3: Code Graph (Part 1)** (Weeks 44-51)
  - Enhanced graph extraction
  - Graph-powered search
  - Impact analysis

### Year 2: Scale & Enterprise

**Q1 2027**

- **EP-3: Code Graph (Part 2)**

  - Visual graph explorer
  - Architectural insights
  - Time-travel code graph

- **EP-4: Multi-Repo Intelligence**
  - Cross-repo dependencies
  - Unified search
  - Workspace management

**Q2 2027**

- **EP-8: Enterprise Security**
  - Authentication & RBAC
  - Encryption & secrets management
  - Audit logging
  - Compliance preparation

**Q3 2027**

- **EP-9: Web Portal**
  - Core search interface
  - Code viewer
  - Repository browser
  - AI integration

**Q4 2027**

- **EP-10: Collaboration Features**
  - Shared annotations
  - Team knowledge graph
  - Code tours
  - Team insights

---

## Conclusion

These 10 strategic enhancement projects provide a comprehensive roadmap to transform Dolphin from an experimental tool into a production-grade, enterprise-ready AI-enabled code intelligence platform. Each project has been carefully designed with:

- **Clear vision** of the desired outcome
- **Broad specification** covering key features and components
- **Detailed questions** to guide implementation decisions
- **Phased approach** enabling incremental delivery
- **Success criteria** for measuring impact

**Next Steps:**

1. Review and prioritize projects based on business goals
2. Validate technical assumptions through prototyping
3. Gather stakeholder feedback and requirements
4. Create detailed project plans for top 3 priorities
5. Begin implementation following the recommended order

**Key Success Factors:**

- Maintain backward compatibility throughout changes
- Keep experimental features opt-in to reduce risk
- Measure impact with evaluation framework (EP-5) before full rollout
- Engage community for feedback and contributions
- Document decisions and learnings for future reference

---

**Document Prepared By**: Claude (Dolphin Codebase Reviewer)
**Review Date**: 2025-11-11
**Next Review**: Quarterly or on major version milestone
