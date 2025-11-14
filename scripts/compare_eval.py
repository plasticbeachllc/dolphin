#!/usr/bin/env python3
"""Compare two retrieval evaluation results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def compare_metric(
    baseline: float,
    current: float,
    threshold: float,
    direction: str = "higher_is_better",
) -> dict[str, Any]:
    """Compare a single metric."""
    diff = current - baseline
    pct_change = (diff / baseline) * 100 if baseline > 0 else 0

    if direction == "higher_is_better":
        regression = diff < -(baseline * threshold / 100)
        improvement = diff > (baseline * threshold / 100)
    else:  # lower_is_better
        regression = diff > (baseline * threshold / 100)
        improvement = diff < -(baseline * threshold / 100)

    return {
        "baseline": baseline,
        "current": current,
        "diff": diff,
        "pct_change": pct_change,
        "regression": regression,
        "improvement": improvement,
        "status": ("regression" if regression else ("improvement" if improvement else "stable")),
    }


def compare_evaluations(baseline_path: Path, current_path: Path, threshold: float) -> dict[str, Any]:
    """Compare two evaluation results."""
    with open(baseline_path) as f:
        baseline = json.load(f)

    with open(current_path) as f:
        current = json.load(f)

    comparison: dict[str, Any] = {
        "baseline_file": str(baseline_path),
        "current_file": str(current_path),
        "baseline_timestamp": baseline.get("timestamp"),
        "current_timestamp": current.get("timestamp"),
        "threshold": threshold,
        "metrics": {},
        "summary": {"regressions": [], "improvements": [], "status": "pass"},
    }

    # Compare overall metrics
    baseline_metrics = baseline["summary"]["metrics"]
    current_metrics = current["summary"]["metrics"]

    for metric in ["mrr", "map", "p@5", "p@10", "r@10"]:
        if metric in baseline_metrics and metric in current_metrics:
            result = compare_metric(
                baseline_metrics[metric],
                current_metrics[metric],
                threshold,
                "higher_is_better",
            )
            comparison["metrics"][metric] = result

            if result["regression"]:
                comparison["summary"]["regressions"].append(metric)
            elif result["improvement"]:
                comparison["summary"]["improvements"].append(metric)

    # Compare pass rates
    baseline_pass_rate = baseline["summary"].get("pass_rate", 0)
    current_pass_rate = current["summary"].get("pass_rate", 0)

    comparison["pass_rate"] = compare_metric(baseline_pass_rate, current_pass_rate, threshold, "higher_is_better")

    # Find newly failing and newly passing scenarios
    baseline_scenarios = {s["id"]: s for s in baseline.get("scenarios", [])}
    current_scenarios = {s["id"]: s for s in current.get("scenarios", [])}

    newly_failing = []
    newly_passing = []

    for scenario_id in baseline_scenarios:
        if scenario_id in current_scenarios:
            baseline_status = baseline_scenarios[scenario_id]["status"]
            current_status = current_scenarios[scenario_id]["status"]

            if baseline_status == "pass" and current_status == "fail":
                newly_failing.append(scenario_id)
            elif baseline_status == "fail" and current_status == "pass":
                newly_passing.append(scenario_id)

    comparison["scenario_changes"] = {
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
    }

    # Determine overall status
    if comparison["summary"]["regressions"] or newly_failing:
        comparison["summary"]["status"] = "fail"

    return comparison


def print_comparison(comparison: dict):
    """Print comparison results."""
    print("=" * 80)
    print("EVALUATION COMPARISON")
    print("=" * 80)

    print(f"\nBaseline: {comparison['baseline_file']}")
    if comparison.get("baseline_timestamp"):
        print(f"  Timestamp: {comparison['baseline_timestamp']}")

    print(f"\nCurrent:  {comparison['current_file']}")
    if comparison.get("current_timestamp"):
        print(f"  Timestamp: {comparison['current_timestamp']}")

    print(f"\nThreshold: {comparison['threshold']}%")

    # Metrics comparison
    print("\nOverall metrics:")
    for metric, data in comparison["metrics"].items():
        arrow = "📈" if data["pct_change"] > 0 else "📉" if data["pct_change"] < 0 else "➡️"
        status_icon = "❌" if data["regression"] else "✅" if data["improvement"] else "➡️"

        print(
            f"  {metric.upper()}: {data['baseline']:.3f} → {data['current']:.3f} "
            f"({arrow} {abs(data['pct_change']):.1f}%) {status_icon}"
        )

    # Pass rate
    if "pass_rate" in comparison:
        pr = comparison["pass_rate"]
        arrow = "📈" if pr["pct_change"] > 0 else "📉" if pr["pct_change"] < 0 else "➡️"
        status_icon = "❌" if pr["regression"] else "✅" if pr["improvement"] else "➡️"
        print(
            f"  Pass rate: {pr['baseline']:.1%} → {pr['current']:.1%} "
            f"({arrow} {abs(pr['pct_change']):.1f}%) {status_icon}"
        )

    # Scenario changes
    changes = comparison["scenario_changes"]
    if changes["newly_failing"]:
        print(f"\n❌ Newly failing scenarios ({len(changes['newly_failing'])}):")
        for scenario_id in changes["newly_failing"]:
            print(f"  - {scenario_id}")

    if changes["newly_passing"]:
        print(f"\n✅ Newly passing scenarios ({len(changes['newly_passing'])}):")
        for scenario_id in changes["newly_passing"]:
            print(f"  + {scenario_id}")

    # Summary
    print("\n" + "=" * 80)
    if comparison["summary"]["status"] == "pass":
        print("Status: ✅ PASS - No significant regressions")
    else:
        print("Status: ❌ FAIL - Regressions detected")

    if comparison["summary"]["regressions"]:
        print("\nRegressed metrics:")
        for metric in comparison["summary"]["regressions"]:
            data = comparison["metrics"][metric]
            print(f"  - {metric.upper()}: {data['pct_change']:+.1f}%")

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Compare two retrieval evaluation results")
    parser.add_argument("baseline", type=Path, help="Baseline evaluation results (JSON)")
    parser.add_argument("current", type=Path, help="Current evaluation results (JSON)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="Regression threshold percentage (default: 5%%)",
    )
    parser.add_argument("--output", type=Path, help="Output JSON file for comparison results")
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with error code if regressions detected",
    )

    args = parser.parse_args()

    # Load and compare
    comparison = compare_evaluations(args.baseline, args.current, args.threshold)

    # Print results
    print_comparison(comparison)

    # Save output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(comparison, f, indent=2)
        print(f"\nComparison saved to: {args.output}")

    # Exit with error if requested and regressions found
    if args.fail_on_regression and comparison["summary"]["status"] == "fail":
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
