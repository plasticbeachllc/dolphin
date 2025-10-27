#!/usr/bin/env python3
"""Enhanced test runner with pytest integration and coverage."""

import subprocess
import sys
from pathlib import Path


def run_tests_with_coverage() -> bool:
    """Run tests with coverage and generate reports."""
    
    # Create reports directory if it doesn't exist
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    cmd = [
        "pytest", 
        "tests/",
        "-v",
        "--cov=src/pb_kb",
        "--cov-report=html:tests/reports/htmlcov",
        "--cov-report=xml:tests/reports/coverage.xml",
        "--cov-report=term-missing",
        "--junitxml=tests/reports/junit/test-results.xml"
    ]
    
    print("Running tests with coverage...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd)
    return result.returncode == 0


def run_legacy_tests() -> bool:
    """Run legacy test runner for backward compatibility."""
    from tests.run_tests import run_all_tests
    return run_all_tests()


def main():
    """Main entry point for test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run KB pipeline tests")
    parser.add_argument(
        "--legacy", 
        action="store_true",
        help="Run legacy test runner instead of pytest"
    )
    parser.add_argument(
        "--both",
        action="store_true", 
        help="Run both legacy and pytest runners"
    )
    
    args = parser.parse_args()
    
    success = True
    
    if args.legacy:
        print("=== Running Legacy Tests ===")
        success = run_legacy_tests()
    elif args.both:
        print("=== Running Legacy Tests ===")
        legacy_success = run_legacy_tests()
        print("\n=== Running Pytest Tests ===")
        pytest_success = run_tests_with_coverage()
        success = legacy_success and pytest_success
    else:
        print("=== Running Pytest Tests ===")
        success = run_tests_with_coverage()
    
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()