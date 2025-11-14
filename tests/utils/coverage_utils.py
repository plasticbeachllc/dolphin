"""Manage test coverage collection and reporting."""

import subprocess
from pathlib import Path


class CoverageManager:
    """Manage test coverage collection and reporting."""

    def __init__(self, source_dir: str = "pb_kb/src", output_dir: Path = None):
        self.source_dir = source_dir
        self.output_dir = output_dir or Path("tests/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def start_coverage(self) -> None:
        """Start coverage collection.

        This is a no-op in the current implementation since we use pytest-cov
        which handles coverage collection automatically.
        """
        pass

    def generate_report(self, output_dir: Path | None = None) -> dict[str, float]:
        """Generate coverage report and return metrics.

        Args:
            output_dir: Directory for coverage reports (default: tests/reports)

        Returns:
            Dictionary with coverage metrics
        """
        output_dir = output_dir or self.output_dir

        # Run coverage report generation
        cmd = [
            "coverage",
            "html",
            "-d",
            str(output_dir / "htmlcov"),
            "--title",
            "KB Pipeline Coverage Report",
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to generate HTML coverage report: {e}")

        # Generate XML report for CI
        xml_cmd = ["coverage", "xml", "-o", str(output_dir / "coverage.xml")]

        try:
            subprocess.run(xml_cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to generate XML coverage report: {e}")

        # Get coverage summary
        return self._get_coverage_summary()

    def _get_coverage_summary(self) -> dict[str, float]:
        """Get coverage summary from coverage tool.

        Returns:
            Dictionary with coverage percentages
        """
        try:
            result = subprocess.run(
                ["coverage", "report", "--format=total"],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse the coverage percentage from output
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "TOTAL" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            coverage_percent = float(parts[-1].rstrip("%"))
                            return {
                                "line_coverage": coverage_percent,
                                "branch_coverage": 0.0,  # Would need branch coverage enabled
                                "overall_coverage": coverage_percent,
                            }
                        except ValueError:
                            pass
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Fallback if coverage tool is not available
        return {"line_coverage": 0.0, "branch_coverage": 0.0, "overall_coverage": 0.0}

    def check_coverage_threshold(self, min_coverage: float = 80.0) -> bool:
        """Check if coverage meets minimum threshold.

        Args:
            min_coverage: Minimum required coverage percentage

        Returns:
            True if coverage meets threshold, False otherwise
        """
        metrics = self._get_coverage_summary()
        current_coverage = metrics.get("overall_coverage", 0.0)

        if current_coverage >= min_coverage:
            print(f"✅ Coverage check passed: {current_coverage:.1f}% >= {min_coverage}%")
            return True
        else:
            print(f"❌ Coverage check failed: {current_coverage:.1f}% < {min_coverage}%")
            return False


def run_tests_with_coverage(
    test_paths: list[str] = None,
    source_dir: str = "pb_kb/src",
    min_coverage: float = 0.0,
    output_dir: Path = None,
) -> bool:
    """Run tests with coverage and generate reports.

    Args:
        test_paths: List of test paths to run (default: ["tests/"])
        source_dir: Source directory to measure coverage for
        min_coverage: Minimum coverage threshold (0 = no threshold)
        output_dir: Output directory for reports

    Returns:
        True if tests passed and coverage meets threshold
    """
    test_paths = test_paths or ["tests/"]
    output_dir = output_dir or Path("tests/reports")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build pytest command with coverage
    cmd = [
        "pytest",
        *test_paths,
        "-v",
        f"--cov={source_dir}",
        f"--cov-report=html:{output_dir}/htmlcov",
        f"--cov-report=xml:{output_dir}/coverage.xml",
        "--cov-report=term-missing",
        f"--junitxml={output_dir}/junit/test-results.xml",
    ]

    # Run the tests
    print(f"Running tests with coverage: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    tests_passed = result.returncode == 0

    # Check coverage if tests passed and threshold is set
    if tests_passed and min_coverage > 0:
        manager = CoverageManager(source_dir, output_dir)
        coverage_ok = manager.check_coverage_threshold(min_coverage)
        return coverage_ok

    return tests_passed
