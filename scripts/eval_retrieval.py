#!/usr/bin/env python3
"""Retrieval evaluation script using golden scenarios.

This script evaluates retrieval quality by running queries from golden
scenarios and computing information retrieval metrics (MRR, P@K, R@K).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.api.app import SearchRequest
from kb.api.search_backend import KnowledgeSearchBackend
from kb.config import KBConfig
from kb.embeddings.provider import create_provider
from kb.store.graph_store import GraphStore
from kb.store.lancedb_store import LanceDBStore
from kb.store.sqlite_meta import SQLiteMetadataStore


class GoldenScenario:
    """A single golden scenario test case."""

    def __init__(self, data: dict[str, Any]):
        self.id = data["id"]
        self.query = data["query"]
        self.repo = data.get("repo", "dolphin")
        self.expected_results = data["expected_results"]
        self.metadata = data.get("metadata", {})

    @property
    def category(self) -> str:
        return self.metadata.get("category", "unknown")

    @property
    def difficulty(self) -> str:
        return self.metadata.get("difficulty", "medium")


class EvaluationMetrics:
    """Container for evaluation metrics."""

    def __init__(self):
        self.mrr_scores: list[float] = []
        self.map_scores: list[float] = []
        self.precision_at_k: dict[int, list[float]] = defaultdict(list)
        self.recall_at_k: dict[int, list[float]] = defaultdict(list)

    def add_scenario_result(
        self,
        reciprocal_rank: float,
        average_precision: float,
        precision_at_k: dict[int, float],
        recall_at_k: dict[int, float],
    ):
        """Add metrics from a single scenario."""
        self.mrr_scores.append(reciprocal_rank)
        self.map_scores.append(average_precision)

        for k, precision in precision_at_k.items():
            self.precision_at_k[k].append(precision)

        for k, recall in recall_at_k.items():
            self.recall_at_k[k].append(recall)

    def compute_summary(self) -> dict[str, float]:
        """Compute summary statistics."""
        summary = {}

        if self.mrr_scores:
            summary["mrr"] = statistics.mean(self.mrr_scores)

        if self.map_scores:
            summary["map"] = statistics.mean(self.map_scores)

        for k in sorted(self.precision_at_k.keys()):
            if self.precision_at_k[k]:
                summary[f"p@{k}"] = statistics.mean(self.precision_at_k[k])

        for k in sorted(self.recall_at_k.keys()):
            if self.recall_at_k[k]:
                summary[f"r@{k}"] = statistics.mean(self.recall_at_k[k])

        return summary


def load_scenarios(path: Path) -> list[GoldenScenario]:
    """Load golden scenarios from file or directory."""
    scenarios = []

    if path.is_file():
        with open(path) as f:
            data = json.load(f)
            # Handle both single scenario and array of scenarios
            if isinstance(data, list):
                scenarios.extend(GoldenScenario(item) for item in data)
            else:
                scenarios.append(GoldenScenario(data))

    elif path.is_dir():
        for json_file in path.rglob("*.json"):
            with open(json_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    scenarios.extend(GoldenScenario(item) for item in data)
                else:
                    scenarios.append(GoldenScenario(data))

    return scenarios


def _extract_path(result: dict[str, Any]) -> str:
    """Return the best-effort file path from a search result."""

    path = result.get("path") or result.get("file")

    if not path:
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            path = metadata.get("path") or metadata.get("file")

    return path or ""


def _extract_symbol(result: dict[str, Any]) -> str:
    """Return the symbol name from a search result if available."""

    symbol = result.get("symbol")

    if not symbol:
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            symbol = metadata.get("symbol")

    return symbol or ""


def match_result(actual: dict, expected: dict) -> bool:
    """Check if an actual result matches an expected result."""
    # Match by file path
    actual_file = actual.get("file", "")
    expected_file = expected.get("file", "")

    if actual_file != expected_file:
        return False

    # If symbol is specified, it must match
    if "symbol" in expected:
        actual_symbol = actual.get("symbol", "")
        expected_symbol = expected["symbol"]
        if actual_symbol != expected_symbol:
            return False

    return True


def evaluate_scenario(scenario: GoldenScenario, backend: KnowledgeSearchBackend, top_k: int = 10) -> dict[str, Any]:
    """Evaluate a single scenario."""
    # Run query
    repo = scenario.repo or ""
    repo_name = repo.split("@", 1)[0].strip()
    repos = [repo_name] if repo_name else None

    request = SearchRequest(
        query=scenario.query,
        top_k=top_k,
        embed_model="large",
        repos=repos,
    )

    try:
        results = backend.search(request)
    except Exception as e:
        return {
            "id": scenario.id,
            "query": scenario.query,
            "category": scenario.category,
            "difficulty": scenario.difficulty,
            "status": "error",
            "error": str(e),
            "metrics": {},
        }

    # Extract file paths and symbols from results
    actual_results = []
    for r in results:
        result_info = {
            "file": _extract_path(r),
            "symbol": _extract_symbol(r),
            "score": r.get("score", 0.0),
        }
        actual_results.append(result_info)

    # Compute metrics
    expected = scenario.expected_results

    # Mean Reciprocal Rank (MRR)
    reciprocal_rank = 0.0
    for rank, actual in enumerate(actual_results, start=1):
        if any(match_result(actual, exp) for exp in expected):
            reciprocal_rank = 1.0 / rank
            break

    # Average Precision (AP)
    relevant_found = 0
    precision_sum = 0.0
    for rank, actual in enumerate(actual_results, start=1):
        if any(match_result(actual, exp) for exp in expected):
            relevant_found += 1
            precision_at_rank = relevant_found / rank
            precision_sum += precision_at_rank

    average_precision = precision_sum / len(expected) if expected else 0.0

    # Precision@K and Recall@K for different K values
    precision_at_k = {}
    recall_at_k = {}

    for k in [5, 10, 20]:
        if k > len(actual_results):
            continue

        # Precision@K
        relevant_in_top_k = sum(
            1 for actual in actual_results[:k] if any(match_result(actual, exp) for exp in expected)
        )
        precision_at_k[k] = relevant_in_top_k / k if k > 0 else 0.0

        # Recall@K
        recall_at_k[k] = relevant_in_top_k / len(expected) if expected else 0.0

    # Determine pass/fail based on difficulty
    thresholds = {
        "easy": {"mrr": 0.90, "p@5": 0.80},
        "medium": {"mrr": 0.80, "p@5": 0.70},
        "hard": {"mrr": 0.70, "p@5": 0.60},
    }

    difficulty = scenario.difficulty
    threshold = thresholds.get(difficulty, thresholds["medium"])

    passed = reciprocal_rank >= threshold["mrr"] and precision_at_k.get(5, 0.0) >= threshold["p@5"]

    return {
        "id": scenario.id,
        "query": scenario.query,
        "category": scenario.category,
        "difficulty": scenario.difficulty,
        "status": "pass" if passed else "fail",
        "metrics": {
            "mrr": reciprocal_rank,
            "map": average_precision,
            "p@5": precision_at_k.get(5, 0.0),
            "p@10": precision_at_k.get(10, 0.0),
            "r@10": recall_at_k.get(10, 0.0),
        },
        "expected_count": len(expected),
        "found_count": sum(1 for actual in actual_results if any(match_result(actual, exp) for exp in expected)),
        "actual_results": actual_results[:5],  # Top 5 for reporting
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality using golden scenarios")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path("golden-scenarios"),
        help="Path to scenarios file or directory",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        help="Path to single scenario file (alternative to --scenarios)",
    )
    parser.add_argument("--output", type=Path, help="Output JSON file for results")
    parser.add_argument("--verbose", action="store_true", help="Show per-query results")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results to retrieve per query")
    parser.add_argument(
        "--store-path",
        type=Path,
        default=Path.home() / ".dolphin" / "knowledge_store",
        help="Path to knowledge store",
    )

    args = parser.parse_args()

    # Load scenarios
    if args.scenario:
        scenarios_path = args.scenario
    else:
        scenarios_path = args.scenarios

    print(f"Loading scenarios from: {scenarios_path}")
    scenarios = load_scenarios(scenarios_path)

    if not scenarios:
        print("No scenarios found!")
        sys.exit(1)

    print(f"Found {len(scenarios)} scenarios")

    # Initialize backend
    print(f"\nInitializing knowledge base from: {args.store_path}")
    config = KBConfig()
    embedding_provider = create_provider(config)  # type: ignore[arg-type]
    lance_store = LanceDBStore(root=args.store_path)
    sql_store = SQLiteMetadataStore(args.store_path / "metadata.db")

    # Try to initialize graph store (optional)
    graph_store = None
    graph_db_path = args.store_path / "graph.db"
    if graph_db_path.exists():
        try:
            graph_store = GraphStore(graph_db_path)
        except Exception:
            pass  # Graph store is optional

    backend = KnowledgeSearchBackend(
        embedding_provider=embedding_provider,
        lance_store=lance_store,
        sql_store=sql_store,
        graph_store=graph_store,
        hybrid_search_enabled=True,
        config=config,
    )

    # Run evaluation
    print("\nRunning evaluation...")
    print("=" * 80)

    results = []
    metrics_by_category = defaultdict(EvaluationMetrics)
    metrics_by_difficulty = defaultdict(EvaluationMetrics)
    overall_metrics = EvaluationMetrics()

    for i, scenario in enumerate(scenarios, 1):
        if args.verbose:
            print(f"\n[{i}/{len(scenarios)}] {scenario.id}")
            print(f'Query: "{scenario.query}"')

        result = evaluate_scenario(scenario, backend, args.top_k)
        results.append(result)

        status = result.get("status", "error")
        metrics = result.get("metrics") or {}

        if status not in {"pass", "fail"}:
            if args.verbose:
                print("Status: ✗ ERROR")
                if error_message := result.get("error"):
                    print(f"Error: {error_message}")
            continue

        reciprocal_rank = metrics.get("mrr", 0.0)
        average_precision = metrics.get("map", 0.0)
        precision_at_k = {
            5: metrics.get("p@5", 0.0),
            10: metrics.get("p@10", 0.0),
        }
        recall_at_k = {
            10: metrics.get("r@10", 0.0),
        }

        overall_metrics.add_scenario_result(
            reciprocal_rank=reciprocal_rank,
            average_precision=average_precision,
            precision_at_k=precision_at_k,
            recall_at_k=recall_at_k,
        )

        metrics_by_category[scenario.category].add_scenario_result(
            reciprocal_rank=reciprocal_rank,
            average_precision=average_precision,
            precision_at_k=precision_at_k,
            recall_at_k=recall_at_k,
        )

        metrics_by_difficulty[scenario.difficulty].add_scenario_result(
            reciprocal_rank=reciprocal_rank,
            average_precision=average_precision,
            precision_at_k=precision_at_k,
            recall_at_k=recall_at_k,
        )

        if args.verbose:
            status_symbol = "✓" if status == "pass" else "✗"
            print(f"Status: {status_symbol} {status.upper()}")
            print(f"MRR: {reciprocal_rank:.3f}, P@5: {precision_at_k[5]:.3f}, R@10: {recall_at_k[10]:.3f}")

    # Compute summary
    overall_summary = overall_metrics.compute_summary()
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nTotal scenarios: {len(scenarios)}")
    print(f"Passed: {passed} ({passed / len(scenarios) * 100:.1f}%)")
    print(f"Failed: {failed} ({failed / len(scenarios) * 100:.1f}%)")
    if errors:
        print(f"Errors: {errors} ({errors / len(scenarios) * 100:.1f}%)")

    print("\nOverall metrics:")
    for metric, value in overall_summary.items():
        target = ""
        if metric == "mrr":
            target = " (target: 0.85)"
            status = "✓" if value >= 0.85 else "✗"
        elif metric == "p@5":
            target = " (target: 0.80)"
            status = "✓" if value >= 0.80 else "✗"
        elif metric == "p@10":
            target = " (target: 0.70)"
            status = "✓" if value >= 0.70 else "✗"
        elif metric == "r@10":
            target = " (target: 0.90)"
            status = "✓" if value >= 0.90 else "✗"
        else:
            status = ""

        print(f"  {metric.upper()}: {value:.3f}{target} {status}")

    # By category
    print("\nBy category:")
    for category, metrics in metrics_by_category.items():
        summary = metrics.compute_summary()
        print(
            "  {category}: MRR {mrr:.3f}, P@5 {p5:.3f}".format(
                category=category,
                mrr=summary.get("mrr", 0.0),
                p5=summary.get("p@5", 0.0),
            )
        )

    # By difficulty
    print("\nBy difficulty:")
    for difficulty, metrics in metrics_by_difficulty.items():
        summary = metrics.compute_summary()
        category_results = [r for r in results if r["difficulty"] == difficulty]
        category_passed = sum(1 for r in category_results if r["status"] == "pass")
        pass_rate = category_passed / len(category_results) if category_results else 0
        print(
            "  {difficulty}: MRR {mrr:.3f}, pass rate {pass_rate:.1%}".format(
                difficulty=difficulty,
                mrr=summary.get("mrr", 0.0),
                pass_rate=pass_rate,
            )
        )

    # Failed scenarios
    failed_scenarios = [r for r in results if r["status"] == "fail"]
    if failed_scenarios:
        print(f"\nFailed scenarios ({len(failed_scenarios)}):")
        for r in failed_scenarios:
            print(f"  - {r['id']} (MRR: {r.get('metrics', {}).get('mrr', 0.0):.3f})")

    # Overall status
    print("\n" + "=" * 80)
    overall_passed = overall_summary.get("mrr", 0) >= 0.85 and overall_summary.get("p@5", 0) >= 0.80
    if overall_passed:
        print("Status: PASS ✓")
    else:
        print("Status: FAIL ✗")
    print("=" * 80)

    # Save results
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "scenarios_path": str(scenarios_path),
            "total_scenarios": len(scenarios),
            "top_k": args.top_k,
        },
        "summary": {
            "total_scenarios": len(scenarios),
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": passed / len(scenarios) if scenarios else 0,
            "metrics": overall_summary,
        },
        "by_category": {category: metrics.compute_summary() for category, metrics in metrics_by_category.items()},
        "by_difficulty": {
            difficulty: metrics.compute_summary() for difficulty, metrics in metrics_by_difficulty.items()
        },
        "scenarios": results,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to: {args.output}")

    # Exit with error if failed
    sys.exit(0 if overall_passed else 1)


if __name__ == "__main__":
    main()
