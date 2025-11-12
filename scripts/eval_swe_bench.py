#!/usr/bin/env python3
"""Evaluate Dolphin on SWE-Bench Lite file identification task.

Compares file identification accuracy against Aider's 70.3% baseline.
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

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.api.app import SearchRequest
from kb.api.search_backend import KnowledgeSearchBackend
from kb.config import KBConfig
from kb.embeddings.provider import create_provider
from kb.store.lancedb_store import LanceDBStore
from kb.store.sqlite_meta import SQLiteMetadataStore
from kb.store.graph_store import GraphStore


def extract_unique_files(results: list[dict], top_k: int = 5) -> list[str]:
    """Extract unique file paths from search results."""
    seen_files = set()
    unique_files = []

    for result in results:
        file_path = result.get("file", "")
        if file_path and file_path not in seen_files:
            seen_files.add(file_path)
            unique_files.append(file_path)
            if len(unique_files) >= top_k:
                break

    return unique_files


def normalize_file_path(path: str, repo_root: Path) -> str:
    """Normalize file path relative to repo root."""
    path = Path(path)

    # Try to make relative to repo root
    try:
        rel_path = path.relative_to(repo_root)
        return str(rel_path)
    except ValueError:
        pass

    # If already relative, return as-is
    if not path.is_absolute():
        return str(path)

    # Otherwise, return filename
    return path.name


def evaluate_instance(
    instance: dict[str, Any],
    backend: KnowledgeSearchBackend,
    repo_root: Path,
    top_k: int = 5,
    verbose: bool = False
) -> dict[str, Any]:
    """Evaluate a single SWE-Bench instance."""
    instance_id = instance["instance_id"]
    problem_statement = instance["problem_statement"]
    gold_files = set(instance.get("changed_files", []))

    if verbose:
        print(f"\n{'='*80}")
        print(f"Instance: {instance_id}")
        print(f"Problem: {problem_statement[:200]}...")
        print(f"Gold files: {', '.join(gold_files)}")

    # Run search query
    try:
        request = SearchRequest(
            query=problem_statement,
            top_k=top_k * 3,  # Get more results, then collapse to files
            embed_model="small"  # Use small model for all
        )

        results = backend.search(request)

        # Extract unique file paths
        predicted_files = extract_unique_files(results, top_k=top_k)

        if verbose:
            print(f"Predicted files: {', '.join(predicted_files)}")

        # Normalize paths
        predicted_set = {normalize_file_path(f, repo_root) for f in predicted_files}
        gold_set = {normalize_file_path(f, repo_root) for f in gold_files}

        # Compute metrics
        true_positives = predicted_set & gold_set
        precision = len(true_positives) / len(predicted_set) if predicted_set else 0.0
        recall = len(true_positives) / len(gold_set) if gold_set else 0.0

        # Reciprocal rank (position of first correct file)
        reciprocal_rank = 0.0
        for rank, pred_file in enumerate(predicted_files, start=1):
            norm_pred = normalize_file_path(pred_file, repo_root)
            if norm_pred in gold_set:
                reciprocal_rank = 1.0 / rank
                break

        if verbose:
            print(f"Precision@{top_k}: {precision:.3f}")
            print(f"Recall@{top_k}: {recall:.3f}")
            print(f"MRR: {reciprocal_rank:.3f}")

        return {
            "instance_id": instance_id,
            "status": "success",
            "predicted_files": list(predicted_set),
            "gold_files": list(gold_set),
            "true_positives": list(true_positives),
            "metrics": {
                f"precision@{top_k}": precision,
                f"recall@{top_k}": recall,
                "mrr": reciprocal_rank
            }
        }

    except Exception as e:
        if verbose:
            print(f"ERROR: {e}")

        return {
            "instance_id": instance_id,
            "status": "error",
            "error": str(e),
            "metrics": {
                f"precision@{top_k}": 0.0,
                f"recall@{top_k}": 0.0,
                "mrr": 0.0
            }
        }


def load_swe_bench_instances(dataset_path: Path, repo_filter: list[str] = None) -> list[dict]:
    """Load SWE-Bench Lite instances, optionally filtered by repo."""
    # Try loading from HuggingFace datasets
    try:
        from datasets import load_dataset
        dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")

        instances = []
        for item in dataset:
            if repo_filter and item["repo"] not in repo_filter:
                continue
            instances.append({
                "instance_id": item["instance_id"],
                "repo": item["repo"],
                "base_commit": item["base_commit"],
                "problem_statement": item["problem_statement"],
                "changed_files": item.get("changed_files", [])
            })

        return instances

    except Exception as e:
        print(f"Warning: Could not load from HuggingFace: {e}")

    # Fallback: Load from local file
    if dataset_path.exists():
        with open(dataset_path) as f:
            data = json.load(f)
            if repo_filter:
                return [
                    inst for inst in data
                    if inst["repo"] in repo_filter
                ]
            return data

    raise FileNotFoundError(
        f"Could not load SWE-Bench instances from {dataset_path}. "
        "Run setup first or download dataset."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Dolphin on SWE-Bench Lite file identification"
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("test-data/swe_bench_instances.json"),
        help="Path to SWE-Bench instances"
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        help="Filter to specific repos (e.g., django/django)"
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path("test-repos/swe-bench"),
        help="Directory containing cloned repos"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of files to predict (default: 5)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file for results"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed per-instance output"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of instances to evaluate"
    )

    args = parser.parse_args()

    # Load instances
    print("Loading SWE-Bench Lite instances...")
    try:
        instances = load_swe_bench_instances(args.dataset, args.repos)
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    if args.limit:
        instances = instances[:args.limit]

    print(f"Loaded {len(instances)} instances")

    if args.repos:
        print(f"Filtered to repos: {', '.join(args.repos)}")

    # Initialize backend
    print("Initializing search backend...")
    config = KBConfig()
    lance_store = LanceDBStore(root=config.lancedb_path)
    sql_store = SQLiteMetadataStore(config.sqlite_db_path)
    graph_store = GraphStore(config.sqlite_db_path)
    provider = create_provider(config)

    backend = KnowledgeSearchBackend(
        lance_store=lance_store,
        sql_store=sql_store,
        graph_store=graph_store,
        provider=provider,
        config=config
    )

    # Evaluate each instance
    print(f"\n{'='*80}")
    print(f"EVALUATING {len(instances)} INSTANCES")
    print(f"{'='*80}")

    results = []
    metrics_by_repo = defaultdict(lambda: {"precision": [], "recall": [], "mrr": []})

    for i, instance in enumerate(instances, 1):
        repo = instance["repo"]
        repo_root = args.repos_dir / repo.replace("/", "__")

        if not args.verbose:
            print(f"[{i}/{len(instances)}] {instance['instance_id']}...", end="", flush=True)

        result = evaluate_instance(
            instance,
            backend,
            repo_root,
            top_k=args.top_k,
            verbose=args.verbose
        )

        results.append(result)

        # Track metrics by repo
        if result["status"] == "success":
            metrics = result["metrics"]
            metrics_by_repo[repo]["precision"].append(metrics[f"precision@{args.top_k}"])
            metrics_by_repo[repo]["recall"].append(metrics[f"recall@{args.top_k}"])
            metrics_by_repo[repo]["mrr"].append(metrics["mrr"])

        if not args.verbose:
            status = "✓" if result["status"] == "success" else "✗"
            mrr = result["metrics"]["mrr"]
            print(f" {status} MRR: {mrr:.3f}")

    # Compute aggregate metrics
    print(f"\n{'='*80}")
    print("RESULTS")
    print(f"{'='*80}\n")

    all_precision = [r["metrics"][f"precision@{args.top_k}"] for r in results if r["status"] == "success"]
    all_recall = [r["metrics"][f"recall@{args.top_k}"] for r in results if r["status"] == "success"]
    all_mrr = [r["metrics"]["mrr"] for r in results if r["status"] == "success"]

    avg_precision = statistics.mean(all_precision) if all_precision else 0.0
    avg_recall = statistics.mean(all_recall) if all_recall else 0.0
    avg_mrr = statistics.mean(all_mrr) if all_mrr else 0.0

    print(f"Overall Metrics:")
    print(f"  Precision@{args.top_k}: {avg_precision:.3f}")
    print(f"  Recall@{args.top_k}: {avg_recall:.3f}")
    print(f"  MRR: {avg_mrr:.3f}")
    print(f"  Success rate: {len(all_precision)}/{len(results)} ({len(all_precision)/len(results)*100:.1f}%)")

    # Aider baseline comparison
    print(f"\nComparison to Aider Baseline:")
    print(f"  Aider P@5: 0.703 (70.3%)")
    print(f"  Dolphin P@{args.top_k}: {avg_precision:.3f} ({avg_precision*100:.1f}%)")

    if avg_precision > 0.703:
        diff = (avg_precision - 0.703) * 100
        print(f"  ✅ Dolphin is {diff:.1f}% better than Aider")
    elif avg_precision < 0.703:
        diff = (0.703 - avg_precision) * 100
        print(f"  ❌ Dolphin is {diff:.1f}% worse than Aider")
    else:
        print(f"  ➡️  Dolphin matches Aider baseline")

    # Per-repo breakdown
    if len(metrics_by_repo) > 1:
        print(f"\nPer-Repo Breakdown:")
        for repo in sorted(metrics_by_repo.keys()):
            metrics = metrics_by_repo[repo]
            repo_precision = statistics.mean(metrics["precision"])
            repo_recall = statistics.mean(metrics["recall"])
            repo_mrr = statistics.mean(metrics["mrr"])
            print(f"  {repo:40} P@{args.top_k}: {repo_precision:.3f}, R@{args.top_k}: {repo_recall:.3f}, MRR: {repo_mrr:.3f}")

    # Save results
    if args.output:
        output_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config": {
                "top_k": args.top_k,
                "total_instances": len(instances),
                "repos_evaluated": list(metrics_by_repo.keys())
            },
            "summary": {
                f"precision@{args.top_k}": avg_precision,
                f"recall@{args.top_k}": avg_recall,
                "mrr": avg_mrr,
                "success_rate": len(all_precision) / len(results) if results else 0.0,
                "aider_baseline": 0.703,
                "vs_aider": avg_precision - 0.703
            },
            "by_repo": {
                repo: {
                    f"precision@{args.top_k}": statistics.mean(metrics["precision"]),
                    f"recall@{args.top_k}": statistics.mean(metrics["recall"]),
                    "mrr": statistics.mean(metrics["mrr"]),
                    "count": len(metrics["precision"])
                }
                for repo, metrics in metrics_by_repo.items()
            },
            "instances": results
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"\n✅ Results saved to: {args.output}")

    print(f"\n{'='*80}")
    return 0 if avg_precision >= 0.703 else 1


if __name__ == "__main__":
    sys.exit(main())
