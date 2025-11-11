I'll help you design a comprehensive benchmarking strategy for your chunking and graph extraction capabilities. Let me first check what's already documented in your project knowledge about these systems.Based on my review of your project knowledge, I'll design a comprehensive benchmarking strategy for your chunking and graph extraction capabilities. Your system is well-positioned with tree-sitter-based chunking and plans for advanced graph intelligence, so let's create benchmarks that will drive evidence-based improvements.

## Comprehensive Benchmarking Strategy for Dolphin

### Executive Summary

Your benchmarking strategy should follow a **three-tier pyramid approach**:

1. **Foundation Layer**: Unit-level chunking quality and graph extraction accuracy
2. **Integration Layer**: End-to-end retrieval effectiveness (this is what matters most)
3. **Comparative Layer**: Benchmarking against reference implementations (Aider, Cline, etc.)

The key insight from your research synthesis: **retrieval quality matters more than chunking perfection**. A perfect chunker that produces poor search results has failed. Let's design benchmarks that measure what actually drives user value.

---

## 1. Chunking Quality Benchmarks

### 1.1 Semantic Boundary Accuracy

**Goal**: Validate that tree-sitter parsing creates semantically meaningful chunks

**Datasets**:

```python
# Create gold-standard chunking datasets
benchmark_repos = {
    "python": [
        "flask/flask",           # Web framework patterns
        "numpy/numpy",           # Scientific computing
        "anthropics/anthropic-sdk-python"  # API client patterns
    ],
    "typescript": [
        "microsoft/vscode",      # Extension patterns
        "facebook/react",        # UI library patterns
        "kilocode/kilocode"      # Your reference implementation
    ]
}
```

**Metrics**:

```python
def chunk_quality_metrics(chunks: list[Chunk]) -> dict:
    return {
        # Completeness: Does chunk contain full semantic unit?
        "complete_functions": count_complete_vs_partial(chunks, "function"),
        "complete_classes": count_complete_vs_partial(chunks, "class"),

        # Boundary precision: No mid-function cuts
        "clean_boundaries": count_clean_vs_broken_boundaries(chunks),

        # Context preservation: Critical context included
        "has_imports": count_chunks_with_imports(chunks),
        "has_docstrings": count_chunks_with_docstrings(chunks),
        "has_type_hints": count_chunks_with_type_hints(chunks),

        # Size distribution
        "token_distribution": get_token_size_distribution(chunks),
        "target_size_adherence": pct_within_range(chunks, 300, 700),
    }
```

**Automated Tests**:

```python
@pytest.mark.parametrize("file_path", get_benchmark_files("python"))
def test_python_chunker_semantic_boundaries(file_path):
    """Chunker should never split functions mid-definition."""
    chunker = PythonChunker()
    with open(file_path) as f:
        chunks = chunker.chunk(f.read())

    for chunk in chunks:
        # Parse chunk with tree-sitter
        tree = parse_python(chunk.content)

        # Check: No partial function definitions
        partial_funcs = find_partial_functions(tree)
        assert len(partial_funcs) == 0, \
            f"Found {len(partial_funcs)} partial functions in chunk"

        # Check: All functions are complete
        complete_funcs = find_complete_functions(tree)
        if complete_funcs:
            assert all(f.is_complete for f in complete_funcs)
```

### 1.2 Deduplication Effectiveness

**Goal**: Validate that content-based hashing prevents redundant embeddings

**Metrics**:

```python
def deduplication_metrics(repo_path: str) -> dict:
    """Measure deduplication effectiveness."""

    # Index repo
    pipeline = IndexingPipeline(repo_path)
    result = pipeline.run()

    # Analyze duplication
    content_hashes = get_all_content_hashes()
    location_count = get_chunk_location_count()

    return {
        "unique_chunks": len(content_hashes),
        "total_locations": location_count,
        "dedup_ratio": location_count / len(content_hashes),

        # Cost savings
        "embeddings_saved": location_count - len(content_hashes),
        "cost_saved_usd": calculate_embedding_cost_saved(),

        # Common duplicates
        "top_duplicates": get_most_duplicated_chunks(top_k=10),
    }
```

**Test Cases**:

- Monorepos with shared utility files
- Forked codebases with minimal changes
- Auto-generated code (protobuf, GraphQL schemas)
- Copy-pasted boilerplate

### 1.3 Language Coverage & Fallback Quality

**Goal**: Ensure fallback chunker handles unsupported languages gracefully

**Test Matrix**:

```python
language_coverage = {
    "tier_1": ["python", "typescript", "javascript"],  # Tree-sitter
    "tier_2": ["markdown", "json", "yaml"],             # Specialized
    "tier_3": ["rust", "go", "java", "c++"],            # Future tree-sitter
    "tier_4": ["sql", "dockerfile", "nginx.conf"],      # Fallback
}

def test_fallback_quality():
    """Fallback chunker should produce reasonable results."""
    for lang, files in get_test_files_by_language().items():
        if lang in tier_4:  # No tree-sitter parser
            chunker = FallbackChunker(target_size=500)

            for file in files:
                chunks = chunker.chunk(file)

                # Even without AST, should have reasonable properties
                assert all(300 <= len(c.content) <= 700 for c in chunks)
                assert not has_mid_line_breaks(chunks)
                assert has_overlapping_context(chunks, overlap_tokens=50)
```

---

## 2. Graph Extraction Benchmarks

### 2.1 Call Graph Accuracy

**Goal**: Measure precision/recall of function call relationships

**Gold Standard Dataset**:

```python
# Manually annotate call graphs for benchmark repos
gold_standard_call_graph = {
    "flask/app.py": {
        "route()": ["add_url_rule()"],
        "add_url_rule()": ["_endpoint_from_view_func()"],
        # ... complete call graph
    }
}

def call_graph_metrics(extracted_graph, gold_graph) -> dict:
    """Compare extracted vs. gold standard call graph."""

    extracted_edges = set(extracted_graph.edges)
    gold_edges = set(gold_graph.edges)

    tp = extracted_edges & gold_edges
    fp = extracted_edges - gold_edges
    fn = gold_edges - extracted_edges

    return {
        "precision": len(tp) / (len(tp) + len(fp)),
        "recall": len(tp) / (len(tp) + len(fn)),
        "f1": 2 * precision * recall / (precision + recall),

        # Error analysis
        "false_positives": list(fp)[:10],
        "false_negatives": list(fn)[:10],
    }
```

**Test Cases**:

- Direct function calls
- Method calls on objects
- Imported functions from other modules
- Higher-order functions (callbacks)
- Async/await chains
- Dynamic calls (getattr, **call**)

### 2.2 Dependency Graph Completeness

**Goal**: Validate import/dependency tracking

**Metrics**:

```python
def dependency_metrics(repo_path: str) -> dict:
    """Analyze dependency graph extraction."""

    graph = extract_dependency_graph(repo_path)

    return {
        # Completeness
        "modules_covered": len(graph.nodes),
        "import_edges": count_edges_by_type(graph, "import"),

        # Graph properties
        "strongly_connected_components": len(find_sccs(graph)),
        "circular_dependencies": find_circular_deps(graph),
        "dead_code_candidates": find_unreachable_nodes(graph),

        # Validation against package manifest
        "matches_requirements_txt": validate_against_manifest(),
        "missing_imports": find_unresolved_imports(),
    }
```

### 2.3 Type Relationship Extraction

**Goal**: Measure accuracy of inheritance/interface relationships

**Python Example**:

```python
def test_inheritance_extraction():
    """Extract class hierarchies accurately."""

    code = """
    class Base:
        pass

    class Child(Base):
        pass

    class GrandChild(Child):
        pass
    """

    graph = extract_type_graph(code)

    assert graph.has_edge("Child", "Base", edge_type="inherits")
    assert graph.has_edge("GrandChild", "Child", edge_type="inherits")

    # Transitive relationships
    ancestors = graph.get_ancestors("GrandChild")
    assert ancestors == {"Child", "Base"}
```

---

## 3. End-to-End Retrieval Benchmarks (Most Critical)

### 3.1 Information Retrieval Metrics

**This is the most important benchmark tier** - it measures actual user value.

**Golden Query Set Construction**:

```python
query_types = {
    "exact_match": [
        "authenticate_user function",
        "DatabaseConnection class",
    ],
    "semantic_search": [
        "how to validate JWT tokens",
        "database connection pooling logic",
    ],
    "cross_file": [
        "all usages of UserModel",
        "API endpoints that modify user data",
    ],
    "architectural": [
        "authentication flow implementation",
        "error handling middleware",
    ]
}

# Manual relevance judgments (5-point scale)
relevance_judgments = {
    ("authenticate_user function", "auth/user.py:45-67"): 5,  # Perfect
    ("authenticate_user function", "auth/jwt.py:12-23"): 3,   # Relevant
    ("authenticate_user function", "utils/hash.py:89-95"): 1, # Marginal
}
```

**Core IR Metrics**:

```python
def compute_retrieval_metrics(query_results, relevance_judgments) -> dict:
    """Industry-standard information retrieval metrics."""

    return {
        # Ranking quality
        "MRR": mean_reciprocal_rank(query_results),
        "MAP": mean_average_precision(query_results),
        "NDCG@5": ndcg_at_k(query_results, k=5),
        "NDCG@10": ndcg_at_k(query_results, k=10),

        # Precision/Recall at K
        "P@1": precision_at_k(query_results, k=1),
        "P@5": precision_at_k(query_results, k=5),
        "P@10": precision_at_k(query_results, k=10),
        "R@10": recall_at_k(query_results, k=10),

        # Coverage
        "zero_result_rate": pct_queries_with_no_results(),
        "result_diversity": mmr_score(query_results),
    }
```

**Automated Regression Testing**:

```python
@pytest.mark.nightly
def test_retrieval_quality_regression():
    """Prevent MRR regressions."""

    baseline_metrics = load_baseline_metrics("v0.1.12")
    current_metrics = run_retrieval_benchmark()

    # Alert on >3% MRR drop
    assert current_metrics["MRR"] >= baseline_metrics["MRR"] * 0.97, \
        f"MRR regression: {current_metrics['MRR']:.3f} < {baseline_metrics['MRR'] * 0.97:.3f}"

    # Alert on >20% latency increase
    assert current_metrics["p95_latency"] <= baseline_metrics["p95_latency"] * 1.2
```

### 3.2 Two-Stage Retrieval Evaluation

**Goal**: Validate vector search + reranking pipeline

**A/B Test Framework**:

```python
retrieval_strategies = {
    "baseline": {
        "vector_only": True,
        "rerank": False,
        "mmr": False,
    },
    "two_stage": {
        "vector_only": False,
        "rerank": True,
        "rerank_top_k": 50,
        "final_k": 10,
    },
    "two_stage_mmr": {
        "vector_only": False,
        "rerank": True,
        "mmr": True,
        "lambda_mmr": 0.7,
    }
}

def run_ablation_study():
    """Test each component's contribution."""

    results = {}
    for strategy_name, config in retrieval_strategies.items():
        metrics = run_benchmark_with_config(config)
        results[strategy_name] = metrics

    # Compare
    df = pd.DataFrame(results).T
    print(df[["MRR", "MAP", "NDCG@10", "p95_latency"]])

    # Statistical significance
    baseline_mrr = results["baseline"]["MRR"]
    for strategy in ["two_stage", "two_stage_mmr"]:
        p_value = ttest_related(results[strategy]["MRR"], baseline_mrr)
        print(f"{strategy} vs baseline: p={p_value:.4f}")
```

### 3.3 Chunking Impact on Retrieval

**Goal**: Measure how chunking quality affects downstream retrieval

**Experiment**:

```python
chunking_strategies = {
    "current": PythonChunker(target_size=500),
    "smaller": PythonChunker(target_size=300),
    "larger": PythonChunker(target_size=800),
    "function_only": PythonChunker(chunk_type="function"),
    "class_level": PythonChunker(chunk_type="class"),
}

def chunking_retrieval_impact():
    """Does chunk size/granularity affect retrieval quality?"""

    results = {}
    for strategy_name, chunker in chunking_strategies.items():
        # Re-index with this chunking strategy
        reindex_with_chunker(chunker)

        # Run retrieval benchmark
        metrics = run_retrieval_benchmark()
        results[strategy_name] = metrics

    # Find optimal chunking strategy
    best_strategy = max(results.items(), key=lambda x: x[1]["MRR"])
    print(f"Best chunking strategy: {best_strategy[0]}")
    print(f"MRR improvement: {best_strategy[1]['MRR'] / results['current']['MRR']:.2%}")
```

---

## 4. Comparative Benchmarking Against Reference Implementations

### 4.1 Aider Repository Maps Comparison

**Goal**: Compare your embeddings-based approach against Aider's tree-sitter repo maps

**Benchmark**:

```python
def compare_with_aider_repo_maps():
    """Head-to-head on file identification task."""

    # Task: Given a natural language query, identify relevant files
    queries = [
        "Where is user authentication implemented?",
        "Find the database connection pooling code",
        "Locate the API rate limiting middleware",
    ]

    # Your approach (embeddings + vector search)
    dolphin_results = []
    for query in queries:
        results = dolphin_search(query, top_k=5)
        dolphin_results.append([r.file_path for r in results])

    # Aider's approach (tree-sitter repo maps + PageRank)
    aider_results = []
    for query in queries:
        results = aider_repo_map_search(query, top_k=5)
        aider_results.append([r.file_path for r in results])

    # Compare against ground truth
    ground_truth = load_ground_truth_files()

    dolphin_metrics = compute_file_identification_metrics(dolphin_results, ground_truth)
    aider_metrics = compute_file_identification_metrics(aider_results, ground_truth)

    print(f"Dolphin Precision@5: {dolphin_metrics['P@5']:.3f}")
    print(f"Aider Precision@5: {aider_metrics['P@5']:.3f}")

    # Aider benchmark: 70.3% on SWE-Bench Lite
    # Your target: Match or exceed on your benchmark repos
```

### 4.2 Hybrid Approach Evaluation

**Based on your research**: Hybrid approach (repo maps + embeddings) is recommended

**Experiment**:

```python
def evaluate_hybrid_approach():
    """Test combining tree-sitter maps with embeddings."""

    strategies = {
        "embeddings_only": lambda q: semantic_search(q),
        "repo_maps_only": lambda q: repo_map_search(q),
        "hybrid_union": lambda q: merge_results([
            semantic_search(q),
            repo_map_search(q)
        ], strategy="union"),
        "hybrid_ranked": lambda q: merge_results([
            semantic_search(q, weight=0.6),
            repo_map_search(q, weight=0.4)
        ], strategy="weighted"),
    }

    # Run on SWE-Bench Lite file identification task
    for strategy_name, search_fn in strategies.items():
        metrics = run_swe_bench_file_identification(search_fn)
        print(f"{strategy_name}: {metrics['accuracy']:.1%}")
```

---

## 5. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

**Priority: Critical**

1. **Create Golden Datasets**:

   ```bash
   # Script to build benchmark datasets
   python scripts/create_benchmark_dataset.py \
     --repos flask,numpy,vscode \
     --queries 500 \
     --output benchmarks/golden/
   ```

2. **Implement Core Metrics**:

   ```python
   # kb/benchmarks/metrics.py
   - mean_reciprocal_rank()
   - mean_average_precision()
   - ndcg_at_k()
   - precision_at_k()
   - recall_at_k()
   ```

3. **Automated Test Suite**:
   ```python
   # tests/benchmarks/test_chunking_quality.py
   # tests/benchmarks/test_retrieval_quality.py
   # tests/benchmarks/test_graph_extraction.py
   ```

### Phase 2: Continuous Evaluation (Week 3-4)

**Priority: High**

1. **CI Integration**:

   ```yaml
   # .github/workflows/benchmark.yml
   - Run quick benchmark on every PR (10 min subset)
   - Full benchmark nightly
   - Regression alerts via Slack/email
   ```

2. **Metrics Dashboard**:

   ```bash
   # Grafana dashboards showing:
   - MRR/MAP trends over time
   - Per-language performance
   - Latency percentiles
   - Cost per query
   ```

3. **A/B Testing Framework**:
   ```python
   # kb/experiments/ab_test.py
   - Traffic splitting
   - Statistical significance testing
   - Experiment tracking database
   ```

### Phase 3: Comparative Analysis (Week 5-6)

**Priority: Medium**

1. **Reference Implementation Comparison**:

   - Set up Aider for head-to-head comparison
   - Run same queries through both systems
   - Analyze strengths/weaknesses

2. **SWE-Bench Lite Evaluation**:

   - File identification accuracy
   - Compare against published benchmarks
   - Identify improvement opportunities

3. **Public Benchmark Results**:
   - Publish results on GitHub
   - Build credibility with metrics
   - Attract contributors

---

## 6. Success Criteria & Target Metrics

### Minimum Viable Benchmarks

```python
target_metrics = {
    # Retrieval quality (most important)
    "MRR": 0.70,              # Mean Reciprocal Rank
    "MAP": 0.65,              # Mean Average Precision
    "NDCG@10": 0.75,          # Normalized DCG at 10
    "P@5": 0.80,              # Precision at 5

    # Coverage
    "zero_result_rate": 0.05, # <5% queries with no results
    "result_diversity": 0.70,  # MMR score

    # Efficiency
    "p50_latency_ms": 300,    # Median search time
    "p95_latency_ms": 1000,   # 95th percentile
    "p99_latency_ms": 2000,   # 99th percentile

    # Chunking quality
    "complete_functions_pct": 0.95,  # 95% complete semantic units
    "clean_boundaries_pct": 0.98,    # 98% clean AST boundaries

    # Graph extraction (when EP-3 is implemented)
    "call_graph_precision": 0.85,
    "call_graph_recall": 0.75,
    "dependency_completeness": 0.90,
}
```

### Regression Thresholds

```python
regression_alerts = {
    "MRR_drop_pct": 3,           # Alert if MRR drops >3%
    "latency_increase_pct": 20,  # Alert if p95 increases >20%
    "zero_results_increase": 5,  # Alert if zero results go up >5 percentage points
}
```

---

## 7. Tools & Infrastructure

### Recommended Stack

```python
benchmarking_stack = {
    "metrics": "scikit-learn, scipy, numpy",
    "datasets": "datasets (HuggingFace), pandas",
    "evaluation": "pytest, pytest-benchmark",
    "visualization": "matplotlib, seaborn, plotly",
    "dashboards": "Grafana + Prometheus",
    "ab_testing": "scipy.stats, mlflow",
    "notebooks": "Jupyter for exploratory analysis",
}
```

### Code Structure

```
benchmarks/
├── datasets/
│   ├── golden/              # Manually curated query-result pairs
│   ├── synthetic/           # Auto-generated queries
│   └── swe_bench_lite/      # SWE-Bench subset
├── metrics/
│   ├── retrieval.py         # IR metrics
│   ├── chunking.py          # Chunking quality
│   └── graph.py             # Graph extraction
├── experiments/
│   ├── ablation_studies.py
│   ├── hyperparameter_tuning.py
│   └── comparative_analysis.py
├── reports/
│   ├── weekly_metrics.md
│   └── regression_analysis/
└── scripts/
    ├── run_benchmark.py
    ├── generate_report.py
    └── compare_with_baseline.py
```

---

## Key Recommendations

1. **Start with retrieval benchmarks** - They measure actual user value
2. **Automate regression detection** - MRR drops >3% should block releases
3. **Compare against Aider's repo maps** - Your research shows this is the key differentiator
4. **Build the hybrid approach** - Repo maps + embeddings is the winning combination
5. **Use SWE-Bench Lite** - Industry-standard benchmark for file identification
6. **Track cost metrics** - Embedding costs matter at scale
7. **Human evaluation loop** - LLM-as-judge for screening, humans for final validation

The most important insight: **Chunking quality only matters if it improves retrieval**. Don't optimize chunking in isolation - always measure downstream impact on MRR/MAP.
