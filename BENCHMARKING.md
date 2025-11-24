# Dolphin Benchmarking Suite

Comprehensive benchmarking and evaluation framework for measuring Dolphin's retrieval quality and performance.

## Overview

The benchmarking suite consists of two complementary approaches:

### 1. **SWE-Bench Lite** (Industry Standard)

- **Task**: File identification for bug fixes
- **Scenarios**: 300 real GitHub issues (75 instances from 10 repos)
- **Comparison**: Direct comparison to Aider (70.3% baseline)
- **Metric**: Precision@K, Recall@K for file-level predictions

### 2. **Custom Golden Scenarios** (Symbol-Level Testing)

- **Task**: Symbol-level code search
- **Scenarios**: 15 curated queries against Flask 2.3.0
- **Coverage**: Exact match, semantic search, framework patterns
- **Metrics**: MRR, MAP, P@K, R@K

---

## Quick Start

### Setup (One-Time)

```bash
# 1. Setup SWE-Bench test repos (10 repos, ~17GB)
just swe-bench-setup

# 2. Setup Flask for golden scenarios (~500MB)
just flask-setup

# Check status
just swe-bench-status
```

### Running Benchmarks

```bash
# Quick smoke test (~5 min)
just benchmark-quick

# Full benchmark suite (~30 min)
just benchmark-full

# Individual evaluations
just eval-swe-bench-quick     # SWE-Bench subset (10 instances)
just eval-golden              # Flask golden scenarios (15)
just benchmark-ann            # ANN parameter tuning

# Compare against baseline
just compare-eval
```

---

## Storage Budget

**Total**: ~40GB allocated

| Component                | Size    | Description                           |
| ------------------------ | ------- | ------------------------------------- |
| **SWE-Bench Source**     | ~5GB    | 10 repos (django, scikit-learn, etc.) |
| **Vector Index (small)** | ~10GB   | 10 repos with 1536-dim embeddings     |
| **Vector Index (large)** | ~3GB    | 3 repos with 3072-dim embeddings      |
| **Metadata (SQLite)**    | ~2GB    | Chunk metadata and FTS                |
| **Graph Store**          | ~2GB    | Code relationships                    |
| **Flask Test Repo**      | ~300MB  | Source + large model index            |
| **Buffer**               | ~17.7GB | Remaining headroom                    |

---

## SWE-Bench Lite Evaluation

### Repository Selection

**10 repos selected** (includes largest SWE-Bench repos):

| Repo                        | Size       | Model     | Instances | Priority          |
| --------------------------- | ---------- | --------- | --------- | ----------------- |
| `django/django`             | Very Large | small     | 45        | Include largest   |
| `scikit-learn/scikit-learn` | Large      | small     | 40        | ML library        |
| `matplotlib/matplotlib`     | Large      | small     | 23        | Plotting          |
| `sympy/sympy`               | Very Large | small     | 35        | Largest codebase  |
| `pytest-dev/pytest`         | Medium     | small     | 18        | Testing framework |
| `sphinx-doc/sphinx`         | Medium     | small     | 16        | Documentation     |
| `pydata/xarray`             | Medium     | small     | 12        | Data arrays       |
| `psf/requests`              | **Small**  | **large** | 15        | HTTP library      |
| `pallets/flask`             | **Small**  | **large** | 10        | Web framework     |
| `mwaskom/seaborn`           | **Small**  | **large** | 8         | Visualization     |

**Coverage**: 222/300 instances (74%)

### Orchestration

The `scripts/orchestrate_swe_bench.py` script handles:

- Cloning repos at specific commits
- Checking out correct SHAs
- Indexing with appropriate embedding models
- State tracking (what's cloned, indexed)

```bash
# Setup all repos
just swe-bench-setup

# Check status
just swe-bench-status

# Manual operations
python scripts/orchestrate_swe_bench.py clone django/django
python scripts/orchestrate_swe_bench.py index django/django --model small
```

### Running Evaluation

```bash
# All instances (~30 min for 222 instances)
just eval-swe-bench

# Specific repos
just eval-swe-bench REPOS="django/django psf/requests"

# Limited subset (for testing)
just eval-swe-bench LIMIT=20

# Quick smoke test (10 instances, ~2 min)
just eval-swe-bench-quick

# Verbose mode (show each instance)
just eval-swe-bench-verbose
```

### Expected Output

```
================================================================================
SWE-BENCH LITE FILE IDENTIFICATION
================================================================================

Evaluated: 75 instances
Average P@5: 0.72 (vs Aider: 0.70)
Average R@5: 0.68
Average MRR: 0.65

Comparison to Aider Baseline:
  Aider P@5: 0.703 (70.3%)
  Dolphin P@5: 0.72 (72.0%)
  ✅ Dolphin is 1.7% better than Aider

Per-Repo Breakdown:
  django/django                            P@5: 0.75, R@5: 0.70, MRR: 0.68
  scikit-learn/scikit-learn                P@5: 0.68, R@5: 0.65, MRR: 0.62
  psf/requests                             P@5: 0.80, R@5: 0.75, MRR: 0.72

✅ Results saved to: results/swe_bench_eval.json
```

---

## Golden Scenarios (Flask)

### Test Repository

**Flask 2.3.0** - Stable web microframework

- **Commit**: `8613e6ab1acc37d8795170f9a3ae918725b1f98f`
- **LOC**: ~15,000
- **Why**: Well-known, clear patterns, stable

### Scenario Distribution (15 total)

| Category               | Count | Difficulty  | Examples                        |
| ---------------------- | ----- | ----------- | ------------------------------- |
| **Exact Match**        | 5     | Easy        | `Flask`, `route`, `Blueprint`   |
| **Description-Based**  | 4     | Medium      | "request context management"    |
| **Semantic**           | 3     | Medium/Hard | "error handler registration"    |
| **Framework-Specific** | 2     | Medium      | Werkzeug integration, Click CLI |
| **Navigation**         | 1     | Hard        | Blueprint registration flow     |

### Setup

```bash
# Clone and index Flask 2.3.0
just flask-setup

# This will:
# 1. Clone pallets/flask
# 2. Checkout tag 2.3.0
# 3. Index with large model (3072-dim for better quality)
```

### Running Evaluation

```bash
# All Flask scenarios
just eval-golden

# Verbose mode
just eval-golden-verbose

# Custom scenario directory
just eval-golden SCENARIOS="path/to/scenarios"
```

### Expected Output

```
================================================================================
RETRIEVAL EVALUATION
================================================================================

Loading scenarios: golden-scenarios-flask/
Found 15 scenarios across 5 categories

Running evaluation...
[████████████████████████████████████████] 15/15

================================================================================
SUMMARY
================================================================================

Total scenarios: 15
Passed: 13 (86.7%)
Failed: 2 (13.3%)

Overall Metrics:
  MRR: 0.867 (target: 0.85) ✓
  MAP: 0.823
  P@5: 0.813 (target: 0.80) ✓
  P@10: 0.733 (target: 0.70) ✓
  R@10: 0.896 (target: 0.90) ✓

By Category:
  exact-match: MRR 0.95, P@5 0.92
  description-based: MRR 0.82, P@5 0.78
  semantic: MRR 0.79, P@5 0.75

Status: PASS ✓
```

---

## ANN Parameter Benchmarking

Tests different ANN configurations to measure latency vs. recall trade-offs.

```bash
# Run ANN benchmarks
just benchmark-ann

# Custom parameters
just benchmark-ann QUERIES=100 ITERATIONS=100
```

### Configurations Tested

| Config            | nprobes | refine_factor | Expected                | Use Case           |
| ----------------- | ------- | ------------- | ----------------------- | ------------------ |
| `default`         | 20      | 10            | Balanced                | Production default |
| `speed`           | 10      | 5             | 2x faster, 95% recall   | Latency-critical   |
| `accuracy`        | 30      | 20            | 99% recall              | Quality-critical   |
| `custom_fast`     | 5       | 3             | 3x faster, 90% recall   | Quick searches     |
| `custom_balanced` | 15      | 8             | 1.5x faster, 97% recall | Good balance       |

### Expected Output

```
================================================================================
ANN PARAMETER BENCHMARKING
================================================================================

Config               p50 (ms)     p95 (ms)     Recall      Speedup
--------------------------------------------------------------------------------
default              42.1         89.7         98.5%       1.00x
speed                30.2         65.3         95.2%       2.05x
accuracy             50.8         105.2        99.1%       0.82x
custom_fast          22.5         48.6         91.3%       2.98x
custom_balanced      35.7         75.1         97.0%       1.49x

Benchmark complete!
```

---

## Regression Detection

### Baseline Management

```bash
# Save current results as baseline
just save-baseline

# Compare new results to baseline
just compare-eval

# Compare specific files
just compare-eval BASELINE=results/old.json CURRENT=results/new.json
```

### Expected Output

```
================================================================================
EVALUATION COMPARISON
================================================================================

Baseline: results/baseline_eval.json
  Timestamp: 2025-11-10 14:30:00

Current:  results/golden_eval.json
  Timestamp: 2025-11-12 10:15:00

Threshold: 3.0%

Overall metrics:
  MRR: 0.850 → 0.867 (📈 2.0%) ✅
  MAP: 0.810 → 0.823 (📈 1.6%) ✅
  P@5: 0.800 → 0.813 (📈 1.6%) ✅
  P@10: 0.720 → 0.733 (📈 1.8%) ✅

Scenario Changes:
  Newly failing: []
  Newly passing: [flask-desc-session-handling]

Status: ✅ PASS (no regressions)
```

### CI Integration (Future)

```yaml
# .github/workflows/benchmark.yml
on: [pull_request]
jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - run: just benchmark-quick
      - run: just compare-eval
      - if: failure()
        run: echo "Benchmark regression detected!"
```

---

## Files and Directory Structure

```
dolphin/
├── scripts/
│   ├── orchestrate_swe_bench.py   # SWE-Bench repo management
│   ├── eval_swe_bench.py          # SWE-Bench evaluation
│   ├── eval_retrieval.py          # Golden scenario evaluation
│   ├── compare_eval.py            # Regression detection
│   └── benchmark_ann.py           # ANN parameter tuning
├── golden-scenarios-flask/        # Flask test scenarios (15)
│   ├── exact-match/
│   ├── description-based/
│   ├── semantic/
│   ├── framework-specific/
│   └── navigation/
├── test-repos/                    # Test repositories
│   ├── swe-bench/                 # SWE-Bench repos
│   │   ├── django__django/
│   │   ├── scikit-learn__scikit-learn/
│   │   └── ...
│   └── flask/                     # Flask 2.3.0
├── test-data/
│   ├── swe_bench_repos.json       # Repo configuration
│   ├── swe_bench_state.json       # Orchestration state
│   └── swe_bench_instances.json   # Evaluation instances
├── results/                       # Benchmark outputs
│   ├── swe_bench_eval.json
│   ├── golden_eval.json
│   ├── ann_benchmark.json
│   └── baselines/                 # Historical baselines
└── BENCHMARKING.md                # This file
```

---

## Maintenance

### Adding New Scenarios

```bash
# 1. Create JSON file in appropriate category
cat > golden-scenarios-flask/exact-match/new-scenario.json <<EOF
{
  "id": "flask-exact-new-function",
  "query": "new_function",
  "repo": "pallets/flask@2.3.0",
  "expected_results": [...],
  "metadata": {...}
}
EOF

# 2. Test the scenario
just eval-golden-verbose
```

### Updating Test Repos

```bash
# Re-clone and re-index a specific repo
rm -rf test-repos/swe-bench/django__django
python scripts/orchestrate_swe_bench.py clone django/django
python scripts/orchestrate_swe_bench.py index django/django --model small
```

### Cleaning Up

```bash
# Remove test repos (saves ~17GB)
rm -rf test-repos/

# Remove results
rm -rf results/

# Remove state tracking
rm test-data/swe_bench_state.json
```

---

## Performance Targets

### SWE-Bench Lite (File Identification)

| Metric  | Aider Baseline | Dolphin Target | Stretch Goal |
| ------- | -------------- | -------------- | ------------ |
| **P@5** | 70.3%          | **> 70%**      | > 75%        |
| **R@5** | N/A            | > 65%          | > 70%        |
| **MRR** | N/A            | > 0.65         | > 0.70       |

### Golden Scenarios (Symbol Search)

| Metric   | Target | Stretch Goal |
| -------- | ------ | ------------ |
| **MRR**  | > 0.85 | > 0.90       |
| **MAP**  | > 0.80 | > 0.85       |
| **P@5**  | > 0.80 | > 0.85       |
| **P@10** | > 0.70 | > 0.75       |
| **R@10** | > 0.90 | > 0.95       |

### ANN Benchmarks (Latency)

| Config       | p50 Target | p95 Target | Recall Target |
| ------------ | ---------- | ---------- | ------------- |
| **Default**  | < 50ms     | < 150ms    | > 95%         |
| **Speed**    | < 30ms     | < 100ms    | > 90%         |
| **Accuracy** | < 100ms    | < 200ms    | > 98%         |

---

## Troubleshooting

### Issue: SWE-Bench repos fail to clone

**Solution**: Check network connectivity, GitHub rate limits

```bash
# Manual clone
git clone https://github.com/django/django.git test-repos/swe-bench/django__django
```

### Issue: Out of storage space

**Solution**: Remove test repos or reduce repo count

```bash
# Check current usage
du -sh test-repos/
du -sh ~/.dolphin/knowledge_store/

# Remove largest repos
rm -rf test-repos/swe-bench/sympy__sympy  # ~100MB
```

### Issue: Evaluation takes too long

**Solution**: Use quick mode or limit instances

```bash
just eval-swe-bench-quick      # Only 10 instances
just eval-swe-bench LIMIT=20   # Custom limit
```

### Issue: Low recall on SWE-Bench

**Solution**: Check that repos are indexed correctly

```bash
just swe-bench-status
uv run python -m kb.cli status  # Check index status
```

---

## Future Enhancements

### Phase 2: Expand Coverage

- [ ] Add 5 more SWE-Bench repos (target: 300/300 instances)
- [ ] Create 15 more golden scenarios (target: 30 total)
- [ ] Add TypeScript test repo (e.g., VSCode extension)

### Phase 3: CI Integration

- [ ] GitHub Actions workflow for benchmarks
- [ ] Automatic regression detection on PRs
- [ ] Performance tracking dashboard
- [ ] Slack/email alerts for regressions

### Phase 4: Advanced Benchmarks

- [ ] Chunking quality metrics
- [ ] Graph extraction accuracy
- [ ] Cross-language search tests
- [ ] Scalability benchmarks (10K+ files)

### Phase 5: Public Benchmarks

- [ ] Publish results on GitHub Pages
- [ ] Create leaderboard (vs Aider, Cline, etc.)
- [ ] Open-source benchmark suite
- [ ] Community contributions

---

## References

- **SWE-Bench Lite**: https://www.swebench.com/
- **Aider Baseline**: 70.3% file identification accuracy
- **Flask 2.3.0**: https://github.com/pallets/flask/tree/2.3.0
- **Benchmarking Plan**: `docs/benchmarking/` (on develop-backend branch)

---

## Questions / Support

- File issues in GitHub with `[benchmark]` tag
- Check `docs/benchmarking/` for detailed methodology
- Run `just -l | grep bench` for all benchmark commands
