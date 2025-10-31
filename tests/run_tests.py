#!/usr/bin/env python3
"""Unified test runner for dolphin project.

This script provides a single entry point for running tests with pytest.
Supports running all tests, only unit tests, only integration tests, or
specific test files/directories.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_tests(
    target: str | None = None,
    coverage: bool = True,
    verbose: bool = True,
    markers: str | None = None,
    parallel: bool = False,
    html_report: bool = False,
) -> bool:
    """Run tests using pytest.

    Args:
        target: Specific test file/directory to run (default: all tests)
        coverage: Enable coverage reporting
        verbose: Enable verbose output
        markers: pytest markers to filter tests (e.g., "not slow")
        parallel: Run tests in parallel with pytest-xdist
        html_report: Generate HTML coverage report

    Returns:
        True if tests passed, False otherwise
    """
    tests_dir = Path(__file__).parent
    reports_dir = tests_dir / "reports"
    reports_dir.mkdir(exist_ok=True)

    # Base command
    cmd = ["pytest"]

    # Target (default to tests directory)
    if target:
        cmd.append(target)
    else:
        cmd.append(str(tests_dir))

    # Verbosity
    if verbose:
        cmd.append("-v")

    # Coverage
    if coverage:
        cmd.extend([
            "--cov=src/pb_kb",
            "--cov-report=term-missing",
        ])
        if html_report:
            cmd.append(f"--cov-report=html:{reports_dir}/htmlcov")
        cmd.append(f"--cov-report=xml:{reports_dir}/coverage.xml")

    # JUnit XML for CI/CD
    cmd.append(f"--junitxml={reports_dir}/junit/test-results.xml")

    # Markers
    if markers:
        cmd.extend(["-m", markers])

    # Parallel execution
    if parallel:
        cmd.extend(["-n", "auto"])

    # Show test durations
    cmd.append("--durations=10")

    print("=" * 70)
    print("Running tests with command:")
    print(" ".join(cmd))
    print("=" * 70)

    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Run dolphin tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests with coverage
  python tests/run_tests.py

  # Run only unit tests
  python tests/run_tests.py --unit

  # Run only integration tests
  python tests/run_tests.py --integration

  # Run specific test file
  python tests/run_tests.py tests/unit/test_hashing.py

  # Run tests in parallel without coverage
  python tests/run_tests.py --parallel --no-coverage

  # Run tests and generate HTML coverage report
  python tests/run_tests.py --html

  # Run fast tests only
  python tests/run_tests.py -m "not slow"
        """,
    )

    parser.add_argument(
        "target",
        nargs="?",
        help="Specific test file or directory to run (default: all tests)",
    )

    parser.add_argument(
        "--unit",
        action="store_true",
        help="Run only unit tests",
    )

    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run only integration tests",
    )

    parser.add_argument(
        "--e2e",
        action="store_true",
        help="Run only end-to-end tests",
    )

    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Disable coverage reporting",
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Reduce output verbosity",
    )

    parser.add_argument(
        "-m", "--markers",
        help="Run tests matching given mark expression (e.g., 'not slow')",
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel (requires pytest-xdist)",
    )

    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML coverage report",
    )

    args = parser.parse_args()

    # Determine target
    target = args.target
    if args.unit:
        target = str(Path(__file__).parent / "unit")
    elif args.integration:
        target = str(Path(__file__).parent / "integration")
    elif args.e2e:
        target = str(Path(__file__).parent / "e2e")

    # Run tests
    success = run_tests(
        target=target,
        coverage=not args.no_coverage,
        verbose=not args.quiet,
        markers=args.markers,
        parallel=args.parallel,
        html_report=args.html,
    )

    if success:
        print("\n" + "=" * 70)
        print("✅ All tests passed!")
        print("=" * 70)
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("❌ Some tests failed!")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
