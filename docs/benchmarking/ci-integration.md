# CI/CD Integration

Guide to automating benchmarking and evaluation in continuous integration pipelines.

## Table of Contents

- [Overview](#overview)
- [CI Strategy](#ci-strategy)
- [GitHub Actions Setup](#github-actions-setup)
- [Benchmark Workflows](#benchmark-workflows)
- [Regression Detection](#regression-detection)
- [Result Reporting](#result-reporting)
- [Performance Tracking](#performance-tracking)
- [Best Practices](#best-practices)

---

## Overview

### Goals

**Automated quality gates**: Catch regressions before they reach production
**Continuous monitoring**: Track performance trends over time
**Fast feedback**: Provide quick results on every PR
**Actionable insights**: Clear reports with recommendations

### CI Tiers

| Tier | When | Duration | Scope | Goal |
|------|------|----------|-------|------|
| **Smoke** | Every commit | < 30s | Basic sanity checks | Catch breaking changes |
| **Quick** | Every PR | < 2min | Fast benchmarks | Early feedback |
| **Full** | Pre-merge | 5-10min | Comprehensive tests | Quality gate |
| **Nightly** | Daily | 30-60min | Extensive analysis | Trend tracking |
| **Weekly** | Weekly | 1-2hr | Deep analysis | Detailed reporting |

---

## CI Strategy

### Benchmark Selection by Tier

#### Smoke Tests (< 30s)
```bash
# Verify basic functionality
- Index small test repo (10 files)
- Run 5 basic queries
- Check p50 latency < 100ms
```

#### Quick Benchmarks (< 2min)
```bash
# Light performance check
- ANN benchmark: 10 queries × 10 iterations
- Eval: 20 core golden scenarios
- Threshold: 10% regression tolerance
```

#### Full Benchmarks (5-10min)
```bash
# Comprehensive testing
- ANN benchmark: 50 queries × 50 iterations
- Eval: All golden scenarios (50+)
- Memory profiling
- Threshold: 5% regression tolerance
```

#### Nightly Benchmarks (30-60min)
```bash
# Extensive analysis
- Large corpus indexing (10K files)
- Load testing (concurrent users)
- Multiple configurations
- Trend analysis
```

#### Weekly Deep Dive (1-2hr)
```bash
# Detailed investigation
- Full efficiency frontier
- Configuration sweep
- Resource profiling
- Comparison reports
```

### Workflow Triggers

```yaml
# Smoke tests
on: [push]

# Quick benchmarks
on: [pull_request]

# Full benchmarks
on:
  pull_request:
    types: [opened, synchronize, ready_for_review]

# Nightly benchmarks
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily

# Weekly deep dive
on:
  schedule:
    - cron: '0 3 * * 0'  # 3 AM Sunday
```

---

## GitHub Actions Setup

### Directory Structure

```
.github/
├── workflows/
│   ├── benchmark-smoke.yml      # Every commit
│   ├── benchmark-quick.yml      # Every PR
│   ├── benchmark-full.yml       # Pre-merge
│   ├── benchmark-nightly.yml    # Daily
│   └── benchmark-weekly.yml     # Weekly
├── actions/
│   ├── setup-benchmarks/        # Reusable setup
│   └── compare-results/         # Reusable comparison
└── scripts/
    └── comment-pr.js            # Post results to PR
```

### Reusable Setup Action

**.github/actions/setup-benchmarks/action.yml**:
```yaml
name: Setup Benchmarks
description: Prepare environment for benchmarking

inputs:
  python-version:
    description: Python version
    default: '3.11'
  cache-key-suffix:
    description: Cache key suffix
    default: ''

runs:
  using: composite
  steps:
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ inputs.python-version }}

    - name: Cache dependencies
      uses: actions/cache@v3
      with:
        path: |
          ~/.cache/pip
          ~/.cache/uv
        key: ${{ runner.os }}-deps-${{ hashFiles('pyproject.toml') }}-${{ inputs.cache-key-suffix }}

    - name: Install dependencies
      shell: bash
      run: |
        pip install uv
        uv pip install -e ".[dev,test]"

    - name: Setup test data
      shell: bash
      run: |
        python scripts/setup_test_data.py

    - name: Download baseline
      shell: bash
      run: |
        mkdir -p baseline
        # Download from artifacts or S3
        python scripts/download_baseline.py
```

---

## Benchmark Workflows

### Smoke Tests

**.github/workflows/benchmark-smoke.yml**:
```yaml
name: Benchmark Smoke Tests

on: [push]

jobs:
  smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 2

    steps:
      - uses: actions/checkout@v3

      - uses: ./.github/actions/setup-benchmarks

      - name: Run smoke tests
        run: |
          python scripts/benchmark_smoke.py --output results/smoke.json

      - name: Check results
        run: |
          python scripts/check_smoke.py results/smoke.json
```

**scripts/benchmark_smoke.py**:
```python
#!/usr/bin/env python3
"""Quick smoke test for benchmarking."""

import json
import sys
import time
from pathlib import Path

def run_smoke_test():
    """Run minimal benchmark smoke test."""
    results = {
        "timestamp": time.time(),
        "tests": []
    }

    # Test 1: Index small repo
    start = time.time()
    # ... index test repo ...
    index_time = time.time() - start
    results["tests"].append({
        "name": "index_small_repo",
        "duration": index_time,
        "status": "pass" if index_time < 5.0 else "fail"
    })

    # Test 2: Basic query
    start = time.time()
    # ... run query ...
    query_time = time.time() - start
    results["tests"].append({
        "name": "basic_query",
        "duration": query_time * 1000,  # ms
        "status": "pass" if query_time < 0.1 else "fail"
    })

    # Write results
    Path("results").mkdir(exist_ok=True)
    with open("results/smoke.json", "w") as f:
        json.dump(results, f, indent=2)

    # Exit with failure if any test failed
    failed = [t for t in results["tests"] if t["status"] == "fail"]
    if failed:
        print(f"❌ {len(failed)} smoke tests failed")
        sys.exit(1)
    else:
        print(f"✓ All {len(results['tests'])} smoke tests passed")

if __name__ == "__main__":
    run_smoke_test()
```

### Quick Benchmarks (PR)

**.github/workflows/benchmark-quick.yml**:
```yaml
name: Quick Benchmarks

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  quick-bench:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - uses: actions/checkout@v3

      - uses: ./.github/actions/setup-benchmarks

      - name: Run quick benchmarks
        run: |
          just benchmark-quick

      - name: Compare to baseline
        id: compare
        run: |
          python scripts/compare_benchmarks.py \
            baseline/quick.json \
            results/quick.json \
            --threshold 10 \
            --output results/comparison.json

      - name: Comment on PR
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const comparison = JSON.parse(fs.readFileSync('results/comparison.json', 'utf8'));
            const comment = require('./.github/scripts/format-benchmark-comment.js')(comparison);

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: comment
            });

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: quick-benchmark-results
          path: results/
```

### Full Benchmarks (Pre-merge)

**.github/workflows/benchmark-full.yml**:
```yaml
name: Full Benchmarks

on:
  pull_request:
    types: [opened, synchronize, ready_for_review]

jobs:
  full-bench:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v3

      - uses: ./.github/actions/setup-benchmarks

      - name: Run performance benchmarks
        run: |
          python scripts/benchmark_ann.py \
            --queries 50 \
            --iterations 50 \
            --output results/performance.json

      - name: Run retrieval evaluation
        run: |
          python scripts/eval_retrieval.py \
            --scenarios golden-scenarios/ \
            --output results/evaluation.json

      - name: Compare to baseline
        id: compare
        run: |
          python scripts/compare_all.py \
            --baseline-dir baseline/ \
            --current-dir results/ \
            --threshold 5 \
            --output results/full_comparison.json

      - name: Check for regressions
        run: |
          python scripts/check_regression.py \
            results/full_comparison.json \
            --fail-on-regression

      - name: Generate report
        run: |
          python scripts/generate_benchmark_report.py \
            results/ \
            --output results/report.html

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: full-benchmark-results
          path: results/

      - name: Comment detailed results
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const comparison = JSON.parse(fs.readFileSync('results/full_comparison.json', 'utf8'));
            const comment = require('./.github/scripts/format-full-comment.js')(comparison);

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: comment
            });
```

### Nightly Benchmarks

**.github/workflows/benchmark-nightly.yml**:
```yaml
name: Nightly Benchmarks

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
  workflow_dispatch:  # Manual trigger

jobs:
  nightly-bench:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - uses: actions/checkout@v3

      - uses: ./.github/actions/setup-benchmarks

      - name: Generate large test corpus
        run: |
          python scripts/generate_test_repo.py \
            --files 10000 \
            --output /tmp/large_corpus

      - name: Run comprehensive benchmarks
        run: |
          python scripts/benchmark_comprehensive.py \
            --corpus /tmp/large_corpus \
            --output results/nightly.json

      - name: Run load tests
        run: |
          python scripts/benchmark_load.py \
            --users 50 \
            --duration 300 \
            --output results/load.json

      - name: Update baseline if improved
        run: |
          python scripts/update_baseline.py \
            results/nightly.json \
            --auto-update-if-improved

      - name: Track trends
        run: |
          python scripts/track_trends.py \
            --results results/nightly.json \
            --history-dir trends/

      - name: Generate trend report
        run: |
          python scripts/generate_trend_report.py \
            trends/ \
            --output results/trends.html

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: nightly-benchmark-${{ github.run_number }}
          path: results/

      - name: Notify on regression
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "🚨 Nightly benchmark regression detected",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "Nightly benchmarks failed. Check results at ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
                  }
                }
              ]
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

---

## Regression Detection

### Comparison Script

**scripts/compare_benchmarks.py**:
```python
#!/usr/bin/env python3
"""Compare benchmark results and detect regressions."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

def compare_metric(
    baseline: float,
    current: float,
    threshold: float,
    direction: str = "lower_is_better"
) -> dict[str, Any]:
    """Compare a single metric."""
    diff = current - baseline
    pct_change = (diff / baseline) * 100 if baseline > 0 else 0

    if direction == "lower_is_better":
        regression = diff > (baseline * threshold / 100)
        improvement = diff < -(baseline * threshold / 100)
    else:  # higher_is_better
        regression = diff < -(baseline * threshold / 100)
        improvement = diff > (baseline * threshold / 100)

    return {
        "baseline": baseline,
        "current": current,
        "diff": diff,
        "pct_change": pct_change,
        "regression": regression,
        "improvement": improvement,
        "status": "regression" if regression else ("improvement" if improvement else "stable")
    }

def compare_benchmarks(baseline_path: Path, current_path: Path, threshold: float):
    """Compare two benchmark results."""
    with open(baseline_path) as f:
        baseline = json.load(f)

    with open(current_path) as f:
        current = json.load(f)

    comparison = {
        "baseline_file": str(baseline_path),
        "current_file": str(current_path),
        "threshold": threshold,
        "metrics": {},
        "summary": {
            "regressions": [],
            "improvements": [],
            "status": "pass"
        }
    }

    # Compare latency metrics
    for metric in ["latency_p50", "latency_p95", "latency_p99"]:
        if metric in baseline and metric in current:
            result = compare_metric(
                baseline[metric],
                current[metric],
                threshold,
                "lower_is_better"
            )
            comparison["metrics"][metric] = result

            if result["regression"]:
                comparison["summary"]["regressions"].append(metric)
            elif result["improvement"]:
                comparison["summary"]["improvements"].append(metric)

    # Compare quality metrics
    for metric in ["mrr", "p@5", "p@10", "r@10"]:
        if metric in baseline and metric in current:
            result = compare_metric(
                baseline[metric],
                current[metric],
                threshold,
                "higher_is_better"
            )
            comparison["metrics"][metric] = result

            if result["regression"]:
                comparison["summary"]["regressions"].append(metric)
            elif result["improvement"]:
                comparison["summary"]["improvements"].append(metric)

    # Determine overall status
    if comparison["summary"]["regressions"]:
        comparison["summary"]["status"] = "fail"

    return comparison

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--threshold", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-regression", action="store_true")

    args = parser.parse_args()

    comparison = compare_benchmarks(args.baseline, args.current, args.threshold)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(comparison, f, indent=2)

    # Print summary
    print(f"Comparison: {comparison['summary']['status'].upper()}")
    print(f"Regressions: {len(comparison['summary']['regressions'])}")
    print(f"Improvements: {len(comparison['summary']['improvements'])}")

    if comparison['summary']['regressions']:
        print("\nRegressed metrics:")
        for metric in comparison['summary']['regressions']:
            info = comparison['metrics'][metric]
            print(f"  - {metric}: {info['pct_change']:+.1f}%")

    # Exit with error if regressions found and flag is set
    if args.fail_on_regression and comparison['summary']['status'] == "fail":
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## Result Reporting

### PR Comment Format

**.github/scripts/format-benchmark-comment.js**:
```javascript
module.exports = function formatBenchmarkComment(comparison) {
  const { metrics, summary } = comparison;

  const statusEmoji = {
    pass: '✅',
    fail: '❌',
    warning: '⚠️'
  };

  let comment = `## ${statusEmoji[summary.status]} Benchmark Results\n\n`;

  // Performance metrics
  comment += `### Performance\n\n`;
  comment += `| Metric | Baseline | Current | Change | Status |\n`;
  comment += `|--------|----------|---------|--------|--------|\n`;

  for (const [name, data] of Object.entries(metrics)) {
    if (name.startsWith('latency_')) {
      const arrow = data.pct_change > 0 ? '📈' : data.pct_change < 0 ? '📉' : '➡️';
      const status = data.regression ? '❌' : data.improvement ? '✅' : '➡️';

      comment += `| ${name} | ${data.baseline.toFixed(1)}ms | ${data.current.toFixed(1)}ms | ${arrow} ${Math.abs(data.pct_change).toFixed(1)}% | ${status} |\n`;
    }
  }

  // Quality metrics
  comment += `\n### Quality\n\n`;
  comment += `| Metric | Baseline | Current | Change | Status |\n`;
  comment += `|--------|----------|---------|--------|--------|\n`;

  for (const [name, data] of Object.entries(metrics)) {
    if (!name.startsWith('latency_')) {
      const arrow = data.pct_change > 0 ? '📈' : data.pct_change < 0 ? '📉' : '➡️';
      const status = data.regression ? '❌' : data.improvement ? '✅' : '➡️';

      comment += `| ${name} | ${data.baseline.toFixed(3)} | ${data.current.toFixed(3)} | ${arrow} ${Math.abs(data.pct_change).toFixed(1)}% | ${status} |\n`;
    }
  }

  // Summary
  if (summary.regressions.length > 0) {
    comment += `\n### ❌ Regressions Detected\n\n`;
    comment += `The following metrics regressed:\n`;
    summary.regressions.forEach(metric => {
      const data = metrics[metric];
      comment += `- **${metric}**: ${data.pct_change > 0 ? '+' : ''}${data.pct_change.toFixed(1)}% (threshold: ${comparison.threshold}%)\n`;
    });
  } else if (summary.improvements.length > 0) {
    comment += `\n### ✅ Improvements\n\n`;
    comment += `Great work! The following metrics improved:\n`;
    summary.improvements.forEach(metric => {
      const data = metrics[metric];
      comment += `- **${metric}**: ${data.pct_change > 0 ? '+' : ''}${data.pct_change.toFixed(1)}%\n`;
    });
  } else {
    comment += `\n### ➡️ Stable Performance\n\nNo significant changes detected.\n`;
  }

  comment += `\n<details><summary>View full results</summary>\n\n`;
  comment += `\`\`\`json\n${JSON.stringify(comparison, null, 2)}\n\`\`\`\n\n`;
  comment += `</details>\n`;

  return comment;
};
```

---

## Performance Tracking

### Trend Database

Store historical results in JSON files or a database:

```
trends/
├── 2025-11-01.json
├── 2025-11-02.json
├── ...
└── index.json  # Metadata
```

**scripts/track_trends.py**:
```python
#!/usr/bin/env python3
"""Track benchmark trends over time."""

import json
from datetime import datetime
from pathlib import Path

def track_trends(results_path: Path, history_dir: Path):
    """Add results to trend history."""
    history_dir.mkdir(exist_ok=True)

    # Load results
    with open(results_path) as f:
        results = json.load(f)

    # Add metadata
    entry = {
        "timestamp": datetime.now().isoformat(),
        "commit": get_git_commit(),
        "metrics": results
    }

    # Save to daily file
    date_str = datetime.now().strftime("%Y-%m-%d")
    daily_file = history_dir / f"{date_str}.json"

    with open(daily_file, "w") as f:
        json.dump(entry, f, indent=2)

    # Update index
    update_index(history_dir)

def get_git_commit():
    """Get current git commit hash."""
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True
        ).strip()
    except:
        return "unknown"

def update_index(history_dir: Path):
    """Update trends index."""
    index_file = history_dir / "index.json"

    # Load existing index
    if index_file.exists():
        with open(index_file) as f:
            index = json.load(f)
    else:
        index = {"entries": []}

    # Add new entries
    for file in sorted(history_dir.glob("*.json")):
        if file.name == "index.json":
            continue

        with open(file) as f:
            data = json.load(f)

        entry = {
            "date": file.stem,
            "timestamp": data.get("timestamp"),
            "commit": data.get("commit"),
            "file": file.name
        }

        # Update or append
        existing = next((e for e in index["entries"] if e["date"] == entry["date"]), None)
        if existing:
            existing.update(entry)
        else:
            index["entries"].append(entry)

    # Sort by date
    index["entries"].sort(key=lambda e: e["date"], reverse=True)

    # Save index
    with open(index_file, "w") as f:
        json.dump(index, f, indent=2)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--history-dir", type=Path, required=True)
    args = parser.parse_args()

    track_trends(args.results, args.history_dir)
```

---

## Best Practices

### Caching

Cache expensive setup steps:

```yaml
- name: Cache test data
  uses: actions/cache@v3
  with:
    path: |
      tests/fixtures/
      ~/.dolphin/test_data/
    key: test-data-${{ hashFiles('scripts/setup_test_data.py') }}
```

### Timeouts

Set realistic timeouts to prevent hanging jobs:

```yaml
jobs:
  benchmark:
    timeout-minutes: 15  # Job-level timeout

    steps:
      - name: Run benchmark
        timeout-minutes: 10  # Step-level timeout
        run: python scripts/benchmark.py
```

### Artifact Retention

Configure artifact retention policies:

```yaml
- name: Upload results
  uses: actions/upload-artifact@v3
  with:
    name: benchmark-results
    path: results/
    retention-days: 30  # Keep for 30 days
```

### Matrix Builds

Test across multiple configurations:

```yaml
strategy:
  matrix:
    python-version: ['3.10', '3.11', '3.12']
    os: [ubuntu-latest, macos-latest]
  fail-fast: false  # Continue even if one fails
```

---

## Summary

**CI tiers**:
- Smoke (< 30s): Every commit
- Quick (< 2min): Every PR
- Full (5-10min): Pre-merge
- Nightly (30-60min): Daily
- Weekly (1-2hr): Weekly deep dive

**Key components**:
- Reusable setup actions
- Comparison scripts
- PR comments
- Trend tracking
- Regression detection

**Best practices**:
- Cache expensive operations
- Set appropriate timeouts
- Use artifact retention
- Fail fast on regressions
- Track trends over time

**Next**: See [Best Practices](./best-practices.md) for general guidelines.
