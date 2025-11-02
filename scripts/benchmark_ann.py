#!/usr/bin/env python3
"""Benchmark script for ANN parameter tuning.

This script benchmarks different ANN configurations to measure:
- Latency (p50, p95, p99)
- Recall (compared to exhaustive search)
- Speedup factor

Usage:
    python scripts/benchmark_ann.py --store-path ~/.dolphin/knowledge_store
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.retrieval.ann_tuning import ANNParams
from kb.store.lancedb_store import LanceDBStore


def benchmark_configuration(
    store: LanceDBStore,
    params: ANNParams,
    queries: list[list[float]],
    iterations: int = 100
) -> dict[str, Any]:
    """Benchmark a specific ANN configuration.
    
    Args:
        store: LanceDB store to query
        params: ANN parameters to test
        queries: List of query vectors
        iterations: Number of iterations per query
    
    Returns:
        Dictionary with benchmark results
    """
    latencies = []
    
    for query in queries:
        # Run multiple iterations for statistical significance
        iter_latencies = []
        for _ in range(iterations):
            start = time.time()
            results = store.query(
                query,
                model="small",
                top_k=10,
                ann_params=params
            )
            iter_latencies.append((time.time() - start) * 1000)
        
        latencies.extend(iter_latencies)
    
    # Calculate statistics
    latencies.sort()
    n = len(latencies)
    
    return {
        "params": {
            "metric": params.metric,
            "nprobes": params.nprobes,
            "refine_factor": params.refine_factor,
            "use_index": params.use_index,
        },
        "latency_p50": statistics.median(latencies),
        "latency_p95": latencies[int(n * 0.95)] if n > 0 else 0,
        "latency_p99": latencies[int(n * 0.99)] if n > 0 else 0,
        "latency_mean": statistics.mean(latencies),
        "latency_stddev": statistics.stdev(latencies) if n > 1 else 0,
        "sample_size": n,
        "estimated_speedup": params.estimated_speedup(),
    }


def benchmark_recall(
    store: LanceDBStore,
    params: ANNParams,
    queries: list[list[float]],
    ground_truth_results: list[set[str]]
) -> float:
    """Benchmark recall for ANN configuration.
    
    Args:
        store: LanceDB store to query
        params: ANN parameters to test
        queries: List of query vectors
        ground_truth_results: List of ground truth result sets (chunk IDs)
    
    Returns:
        Average recall across all queries
    """
    recalls = []
    
    for query, ground_truth in zip(queries, ground_truth_results):
        results = store.query(
            query,
            model="small",
            top_k=10,
            ann_params=params
        )
        
        returned_ids = {r["id"] for r in results}
        
        if ground_truth:
            recall = len(returned_ids & ground_truth) / len(ground_truth)
            recalls.append(recall)
    
    return statistics.mean(recalls) if recalls else 0.0


def generate_test_queries(n: int = 10, dim: int = 1536) -> list[list[float]]:
    """Generate random test query vectors.
    
    Args:
        n: Number of queries to generate
        dim: Vector dimension
    
    Returns:
        List of query vectors
    """
    import random
    queries = []
    for _ in range(n):
        # Generate random normalized vector
        vector = [random.gauss(0, 1) for _ in range(dim)]
        # Normalize
        norm = sum(x**2 for x in vector) ** 0.5
        vector = [x / norm for x in vector]
        queries.append(vector)
    return queries


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark ANN parameter configurations for LanceDB"
    )
    parser.add_argument(
        "--store-path",
        type=Path,
        default=Path.home() / ".dolphin" / "knowledge_store",
        help="Path to LanceDB store"
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=10,
        help="Number of test queries"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="Iterations per query"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file for results"
    )
    
    args = parser.parse_args()
    
    # Initialize store
    print(f"Loading LanceDB store from {args.store_path}")
    store = LanceDBStore(root=args.store_path)
    
    # Generate test queries
    print(f"Generating {args.queries} test queries...")
    queries = generate_test_queries(n=args.queries, dim=1536)
    
    # Get ground truth (exhaustive search)
    print("Computing ground truth with exhaustive search...")
    ground_truth_params = ANNParams.for_development()
    ground_truth_results = []
    for query in queries:
        results = store.query(
            query,
            model="small",
            top_k=10,
            ann_params=ground_truth_params
        )
        ground_truth_results.append({r["id"] for r in results})
    
    # Benchmark configurations
    configs = [
        ("default", ANNParams()),
        ("speed", ANNParams.for_speed()),
        ("accuracy", ANNParams.for_accuracy()),
        ("custom_fast", ANNParams(nprobes=5, refine_factor=3)),
        ("custom_balanced", ANNParams(nprobes=15, refine_factor=8)),
    ]
    
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "num_queries": args.queries,
            "iterations_per_query": args.iterations,
            "vector_dimension": 1536,
        },
        "benchmarks": {}
    }
    
    print("\n" + "=" * 80)
    print("ANN PARAMETER BENCHMARKING")
    print("=" * 80)
    
    for name, params in configs:
        print(f"\nBenchmarking: {name}")
        print(f"  nprobes={params.nprobes}, refine_factor={params.refine_factor}")
        
        # Latency benchmark
        latency_results = benchmark_configuration(
            store, params, queries, args.iterations
        )
        
        # Recall benchmark
        recall = benchmark_recall(
            store, params, queries, ground_truth_results
        )
        
        # Combine results
        benchmark_result = {
            **latency_results,
            "recall": recall
        }
        
        results["benchmarks"][name] = benchmark_result
        
        # Print results
        print(f"  Latency p50: {latency_results['latency_p50']:.1f}ms")
        print(f"  Latency p95: {latency_results['latency_p95']:.1f}ms")
        print(f"  Latency p99: {latency_results['latency_p99']:.1f}ms")
        print(f"  Recall: {recall:.2%}")
        print(f"  Estimated speedup: {latency_results['estimated_speedup']:.2f}x")
    
    # Print comparison table
    print("\n" + "=" * 80)
    print("COMPARISON TABLE")
    print("=" * 80)
    print(f"{'Config':<20} {'p50 (ms)':<12} {'p95 (ms)':<12} {'Recall':<10} {'Speedup':<10}")
    print("-" * 80)
    
    for name, benchmark in results["benchmarks"].items():
        print(
            f"{name:<20} "
            f"{benchmark['latency_p50']:<12.1f} "
            f"{benchmark['latency_p95']:<12.1f} "
            f"{benchmark['recall']:<10.2%} "
            f"{benchmark['estimated_speedup']:<10.2f}x"
        )
    
    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    
    print("\n" + "=" * 80)
    print("Benchmark complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()