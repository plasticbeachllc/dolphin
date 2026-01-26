#!/usr/bin/env python3
"""Analyze SWE-Bench Lite to determine best repos for benchmarking."""

import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    from datasets import load_dataset  # type: ignore[unresolved-import]

    print("Loading SWE-Bench Lite dataset...")
    dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")

    # Analyze repo distribution
    repos = [instance["repo"] for instance in dataset]
    repo_counts = Counter(repos)

    # Group instances by repo
    repo_instances = defaultdict(list)
    for instance in dataset:
        repo_instances[instance["repo"]].append(
            {
                "instance_id": instance["instance_id"],
                "problem_statement": instance["problem_statement"][:100] + "...",
                "base_commit": instance["base_commit"],
            }
        )

    print(f"\n{'=' * 80}")
    print("SWE-BENCH LITE ANALYSIS")
    print(f"{'=' * 80}\n")
    print(f"Total instances: {len(dataset)}")
    print(f"Unique repos: {len(repo_counts)}")
    print("\nTop 15 repos by instance count:\n")

    for repo, count in repo_counts.most_common(15):
        print(f"  {repo:40} {count:3} instances")

    # Save detailed analysis
    output = {
        "total_instances": len(dataset),
        "unique_repos": len(repo_counts),
        "repo_counts": dict(repo_counts),
        "repo_instances": dict(repo_instances),
    }

    output_path = Path("benchmarks/test-data/swe_bench_analysis.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Detailed analysis saved to: {output_path}")

    # Suggest repo selection
    print(f"\n{'=' * 80}")
    print("SUGGESTED REPO SELECTION")
    print(f"{'=' * 80}\n")

    top_10 = repo_counts.most_common(10)
    total_instances = sum(count for _, count in top_10)

    print(
        f"Top 10 repos cover {total_instances}/{len(dataset)} instances ({total_instances / len(dataset) * 100:.1f}%)\n"
    )

    for i, (repo, count) in enumerate(top_10, 1):
        print(f"{i:2}. {repo:40} {count:3} instances")

except ImportError:
    print("ERROR: datasets library not installed")
    print("Run: pip install datasets")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback

    traceback.print_exc()
