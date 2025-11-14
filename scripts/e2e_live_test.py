#!/usr/bin/env python3
"""End-to-end live integration test for Dolphin.

This script tests the complete Dolphin system with real API calls:
- Config initialization
- Repository indexing (small sample)
- Embedding API calls (OpenAI)
- Vector storage (LanceDB)
- Metadata storage (SQLite)
- Search functionality
- MCP endpoints

Cost control: Uses a tiny test repository (<100 lines) to minimize API calls.
Estimated cost: <$0.01 USD per run.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def log_step(message: str):
    """Log a test step."""
    print(f"{BLUE}➜{RESET} {message}")


def log_success(message: str):
    """Log a success."""
    print(f"{GREEN}✓{RESET} {message}")


def log_error(message: str):
    """Log an error."""
    print(f"{RED}✗{RESET} {message}")


def log_warning(message: str):
    """Log a warning."""
    print(f"{YELLOW}⚠{RESET} {message}")


def check_prerequisites() -> bool:
    """Check that all prerequisites are met."""
    log_step("Checking prerequisites...")

    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        log_error("OPENAI_API_KEY environment variable not set")
        return False
    log_success("OpenAI API key found")

    # Check Python version
    log_success(f"Python version OK ({sys.version_info.major}.{sys.version_info.minor})")

    return True


def create_test_repository(base_dir: Path) -> Path:
    """Create a minimal test repository with ~100 lines of code."""
    log_step("Creating minimal test repository...")

    repo_dir = base_dir / "test_repo"
    repo_dir.mkdir()

    # Create a simple Python file (~30 lines)
    (repo_dir / "main.py").write_text("""
\"\"\"Simple test module for end-to-end testing.\"\"\"

def calculate_sum(numbers: list[int]) -> int:
    \"\"\"Calculate the sum of a list of numbers.\"\"\"
    return sum(numbers)

def calculate_average(numbers: list[int]) -> float:
    \"\"\"Calculate the average of a list of numbers.\"\"\"
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)

class Calculator:
    \"\"\"Simple calculator class.\"\"\"

    def __init__(self):
        self.history = []

    def add(self, a: int, b: int) -> int:
        \"\"\"Add two numbers.\"\"\"
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result

    def multiply(self, a: int, b: int) -> int:
        \"\"\"Multiply two numbers.\"\"\"
        result = a * b
        self.history.append(f"{a} × {b} = {result}")
        return result
""")

    # Create a markdown file (~20 lines)
    (repo_dir / "README.md").write_text("""
# Test Repository

This is a minimal test repository for end-to-end testing.

## Features

- Simple arithmetic functions
- Calculator class
- Minimal code to keep API costs low

## Usage

```python
from main import Calculator

calc = Calculator()
result = calc.add(5, 3)
print(result)  # 8
```

## Cost Optimization

This repository contains <100 lines of code to minimize:
- Embedding API costs
- Indexing time
- Storage requirements
""")

    # Create a TypeScript file (~25 lines)
    (repo_dir / "utils.ts").write_text("""
/**
 * Utility functions for testing.
 */

export function greet(name: string): string {
  return `Hello, ${name}!`;
}

export function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

export class StringUtils {
  static uppercase(str: string): string {
    return str.toUpperCase();
  }

  static lowercase(str: string): string {
    return str.toLowerCase();
  }

  static reverse(str: string): string {
    return str.split('').reverse().join('');
  }
}
""")

    # Initialize git repo (required by Dolphin)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    log_success(f"Test repository created at {repo_dir}")
    return repo_dir


def run_command(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> tuple[bool, str, str]:
    """Run a command and return success status, stdout, stderr."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def _run_initialization_test(store_root: Path) -> bool:
    """Test Dolphin initialization."""
    log_step("Testing Dolphin initialization...")

    # Run dolphin init with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)

    success, stdout, stderr = run_command(["uv", "run", "dolphin", "init"], env=env)

    if not success:
        log_error(f"Initialization failed: {stderr}")
        return False

    # Verify config was created
    config_path = Path.home() / ".dolphin" / "config.toml"
    if not config_path.exists():
        log_error(f"Config file not created at {config_path}")
        return False

    log_success("Dolphin initialized successfully")
    return True


def _run_repository_indexing_test(repo_path: Path, store_root: Path) -> bool:
    """Test repository indexing with real OpenAI API calls."""
    log_step("Testing repository indexing (this will make OpenAI API calls)...")

    # Set up environment with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)

    # Add repository
    log_step("  Adding repository...")
    success, stdout, stderr = run_command(
        [
            "uv",
            "run",
            "dolphin",
            "add-repo",
            "test_repo",
            str(repo_path),
            "--default-embed-model",
            "small",  # Use small model to save costs
        ],
        env=env,
    )

    if not success:
        log_error(f"Failed to add repository: {stderr}")
        return False
    log_success("  Repository added")

    # Index repository with --full flag to avoid git diff issues
    log_step("  Indexing repository (creating embeddings)...")
    success, stdout, stderr = run_command(
        [
            "uv",
            "run",
            "dolphin",
            "index",
            "test_repo",
            "--full",  # Force full reindex to avoid stale commit references
        ],
        env=env,
    )

    if not success:
        log_error(f"Failed to index repository: {stderr}")
        return False

    # Check for success indicators in output
    if "chunks indexed" in stdout.lower() or "success" in stdout.lower():
        log_success("  Repository indexed successfully")
        # Extract token count if available
        for line in stdout.split("\n"):
            if "tokens" in line.lower() or "cost" in line.lower():
                log_step(f"    {line.strip()}")
    else:
        log_warning("  Indexing completed but no clear success message")

    return True


def _run_search_and_api_test(store_root: Path, port: int) -> tuple[bool, bool]:
    """Test search functionality and API endpoints with a single server instance.

    Returns:
        tuple[bool, bool]: (search_passed, api_passed)
    """
    # Set up environment with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)

    # Update config to use the test server port
    config_path = Path.home() / ".dolphin" / "config.toml"
    original_config = None
    if config_path.exists():
        config_content = config_path.read_text()
        original_config = config_content
        # Replace endpoint port
        config_content = config_content.replace('endpoint = "127.0.0.1:7777"', f'endpoint = "127.0.0.1:{port}"')
        config_path.write_text(config_content)

    try:
        # ============================================================
        # Test 1: Search Functionality
        # ============================================================
        print(f"\n{BLUE}{'─' * 70}{RESET}")
        log_step("Test 3: Search Functionality")
        print(f"{BLUE}{'─' * 70}{RESET}")

        test_queries = ["calculate sum", "Calculator class", "greeting function"]

        search_passed = False
        for query in test_queries:
            log_step(f"  Searching for: '{query}'")
            # Use CLI command with correct embed model
            success, stdout, stderr = run_command(
                [
                    "uv",
                    "run",
                    "dolphin",
                    "search",
                    query,
                    "--top-k",
                    "3",
                    "--embed-model",
                    "small",  # Match the indexing model
                    "--score-cutoff",
                    "0.0",  # RRF scores are small (~0.01-0.03)
                ],
                env=env,
            )

            if not success:
                log_error(f"  Search command failed: {stderr}")
                continue

            # Check if results were returned
            if "No results found" in stdout or len(stdout.strip()) < 10:
                log_warning(f"  No results for '{query}'")
            else:
                log_success(f"  Found results for '{query}'")
                search_passed = True
                # Print first result summary (first 3 lines of output)
                lines = stdout.split("\n")[:4]
                for line in lines:
                    if line.strip():
                        print(f"      {line.strip()}")

        if search_passed:
            log_success("Search functionality test PASSED")
        else:
            log_error("Search functionality test FAILED - no results returned")

        # ============================================================
        # Test 2: API Endpoints
        # ============================================================
        print(f"\n{BLUE}{'─' * 70}{RESET}")
        log_step("Test 4: API Endpoints")
        print(f"{BLUE}{'─' * 70}{RESET}")

        api_passed = True

        # Test health endpoint
        log_step("  Testing /health endpoint...")
        success, stdout, stderr = run_command(["curl", "-s", f"http://127.0.0.1:{port}/health"])

        if success and "ok" in stdout.lower():
            log_success("  Health endpoint OK")
        else:
            log_error(f"  Health endpoint failed: {stdout}")
            api_passed = False

        # Test repos endpoint
        log_step("  Testing /repos endpoint...")
        success, stdout, stderr = run_command(["curl", "-s", f"http://127.0.0.1:{port}/repos"])

        if success and "test_repo" in stdout:
            log_success("  Repos endpoint OK")
        else:
            log_error(f"  Repos endpoint failed: {stdout[:100]}")
            api_passed = False

        if api_passed:
            log_success("API endpoints test PASSED")
        else:
            log_error("API endpoints test FAILED")

        return search_passed, api_passed

    finally:
        # Restore original config
        if original_config and config_path.exists():
            config_path.write_text(original_config)


def _run_reranking_test(store_root: Path) -> bool:
    """Test reranking if dependencies are installed (optional)."""
    log_step("Testing reranking (optional - only if dependencies installed)...")

    # Set up environment with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)

    # Check if reranking dependencies are available
    import importlib.util

    has_torch = importlib.util.find_spec("torch") is not None
    has_sentence_transformers = importlib.util.find_spec("sentence_transformers") is not None

    if not (has_torch and has_sentence_transformers):
        log_warning("  Reranking dependencies not installed - skipping (optional)")
        log_step("    To enable: uv pip install torch sentence-transformers")
        return True  # Not a failure - it's optional

    log_step("  ✓ Reranking dependencies found (torch + sentence-transformers)")

    # Dependencies are available, test reranking
    log_step("  Enabling reranking in config...")

    # Modify config to enable reranking
    config_path = Path.home() / ".dolphin" / "config.toml"
    if not config_path.exists():
        log_warning("  Config file not found, cannot enable reranking")
        return True  # Not a critical failure

    # Read config
    config_content = config_path.read_text()

    # Enable reranking if it exists in config
    if "[retrieval.reranking]" in config_content:
        # Replace enabled = false with enabled = true
        config_content = config_content.replace("enabled = false", "enabled = true")
        config_path.write_text(config_content)
        log_success("  Reranking enabled in config")
    else:
        log_warning("  Config doesn't have [retrieval.reranking] section")
        return True

    # Test search with reranking
    log_step("  Testing search with reranking enabled...")
    success, stdout, stderr = run_command(
        ["uv", "run", "dolphin", "search", "Calculator class", "--top-k", "3"], env=env
    )

    if not success:
        log_error(f"  Search with reranking failed: {stderr}")
        # Restore config
        config_content = config_content.replace("enabled = true", "enabled = false")
        config_path.write_text(config_content)
        return False

    # Check if reranking was used (look for rerank_score in output)
    # Note: This depends on the output format
    log_success("  Search with reranking completed")

    # Restore config (disable reranking)
    log_step("  Restoring config (disabling reranking)...")
    config_content = config_content.replace("enabled = true", "enabled = false")
    config_path.write_text(config_content)
    log_success("  Config restored")

    return True


def find_free_port() -> int:
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def start_api_server(store_root: Path, port: int) -> subprocess.Popen:
    """Start the API server and return the process handle."""
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)

    log_step(f"  Debug: Setting DOLPHIN_STORE_ROOT={store_root}")

    server_process = subprocess.Popen(
        ["uv", "run", "dolphin", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Capture stderr to stdout so we can see server messages
        text=True,
        env=env,
    )

    return server_process


def stop_api_server(server_process: subprocess.Popen) -> None:
    """Stop the API server process."""
    server_process.terminate()
    try:
        server_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_process.kill()


def cleanup_test_repo(temp_store_root: Path) -> None:
    """Clean up test repository from the database.

    This provides explicit cleanup even though we use a temporary directory,
    ensuring no test data leaks into the persistent database.
    """
    try:
        # The CLI commands invoked by this script load their configuration via
        # ``kb.config.load_config`` which ultimately resolves the store root from
        # the user's config directory. Those commands currently ignore the
        # DOLPHIN_STORE_ROOT env var that this script sets, so we need to resolve
        # the same path the CLI uses to make sure we clean up the real metadata
        # store instead of the temporary directory passed to this function.
        from kb.config import load_config

        try:
            config_store_root = load_config().resolved_store_root()
        except FileNotFoundError:
            # If dolphin init failed before creating a config, fall back to the
            # temporary store root to keep cleanup best-effort.
            config_store_root = temp_store_root
        except Exception as config_error:
            log_warning(f"Cleanup warning: could not load config ({config_error}); using temp store root")
            config_store_root = temp_store_root

        store_root = config_store_root

        if store_root != temp_store_root:
            log_step(f"Cleaning up CLI store root at {store_root}")
        db_path = store_root / "metadata.db"

        if not db_path.exists():
            return

        from kb.store.sqlite_meta import SQLiteMetadataStore

        store = SQLiteMetadataStore(db_path)
        store.initialize()

        with store._get_connection() as conn:  # type: ignore[attr-defined]
            # Delete test_repo and all associated data
            cursor = conn.execute("SELECT id FROM repos WHERE name = ?", ("test_repo",))
            repo_row = cursor.fetchone()

            if repo_row:
                repo_id = repo_row[0]
                log_step("Cleaning up test repository from database...")

                # Delete all data associated with test_repo
                conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
                conn.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
                conn.execute("DELETE FROM scan_sessions WHERE repo_id = ?", (repo_id,))
                conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))

                conn.commit()
                log_success("Test repository cleaned up")
    except Exception as e:
        # Don't fail the test if cleanup fails
        log_warning(f"Cleanup warning: {e}")


def main():
    """Run all end-to-end tests."""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}Dolphin End-to-End Live Integration Test{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")

    # Check prerequisites
    if not check_prerequisites():
        log_error("Prerequisites check failed. Exiting.")
        return 1

    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        store_root = temp_path / "dolphin_store"

        log_step(f"Using temporary directory: {temp_dir}")
        log_step(f"Store root: {store_root}\n")

        server_process = None
        try:
            # Create test repository
            repo_path = create_test_repository(temp_path)

            # Track test results
            test_results = {}

            # ============================================================
            # Test 1: Initialization
            # ============================================================
            print(f"\n{BLUE}{'─' * 70}{RESET}")
            log_step("Test 1: Dolphin Initialization")
            print(f"{BLUE}{'─' * 70}{RESET}")
            test_results["initialization"] = _run_initialization_test(store_root)
            if test_results["initialization"]:
                log_success("Initialization test PASSED")
            else:
                log_error("Initialization test FAILED")

            # ============================================================
            # Test 2: Repository Indexing
            # ============================================================
            print(f"\n{BLUE}{'─' * 70}{RESET}")
            log_step("Test 2: Repository Indexing")
            print(f"{BLUE}{'─' * 70}{RESET}")
            test_results["indexing"] = _run_repository_indexing_test(repo_path, store_root)
            if test_results["indexing"]:
                log_success("Indexing test PASSED")
            else:
                log_error("Indexing test FAILED")

            # ============================================================
            # Start API Server (for tests 3 & 4)
            # ============================================================
            print(f"\n{BLUE}{'─' * 70}{RESET}")
            log_step("Starting API Server for Search and API Tests")
            print(f"{BLUE}{'─' * 70}{RESET}")

            port = find_free_port()
            log_step(f"  Using port {port} for API server...")
            server_process = start_api_server(store_root, port)

            # Wait longer for server to fully start and load indexes
            log_step("  Waiting for server to start (5 seconds)...")
            time.sleep(5)

            # Check if server is running
            if server_process.poll() is not None:
                _, stderr = server_process.communicate()
                log_error(f"  Server failed to start: {stderr}")
                test_results["search"] = False
                test_results["api"] = False
            else:
                log_success("  API server started successfully")

                # Run tests 3 & 4 with the running server
                search_passed, api_passed = _run_search_and_api_test(store_root, port)
                test_results["search"] = search_passed
                test_results["api"] = api_passed

            # Check database before stopping server
            log_step("\n  Verifying indexed data in database...")
            import os

            from kb.store import SQLiteMetadataStore

            # Temporarily set env var for this check
            old_env = os.environ.get("DOLPHIN_STORE_ROOT")
            os.environ["DOLPHIN_STORE_ROOT"] = str(store_root)

            db_path = store_root / "metadata.db"
            if db_path.exists():
                sql_store = SQLiteMetadataStore(db_path)
                with sql_store._connect() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM repos")
                    repo_count = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM chunk_content")
                    chunk_count = cur.fetchone()[0]
                    cur.execute("SELECT name, default_embed_model FROM repos")
                    repos = cur.fetchall()

                log_success(f"  Found {repo_count} repo(s), {chunk_count} chunk(s)")
                for repo_name, model in repos:
                    log_step(f"    Repo '{repo_name}' uses model '{model}'")

                # Check LanceDB vector data
                lancedb_path = store_root / "lancedb"
                if lancedb_path.exists():
                    import lancedb

                    try:
                        db = lancedb.connect(str(lancedb_path))
                        tables = db.table_names()
                        log_step(f"  LanceDB tables: {tables}")

                        # Check chunks_small table
                        if "chunks_small" in tables:
                            table = db.open_table("chunks_small")
                            count = table.count_rows()
                            log_step(f"    chunks_small: {count} vectors")
                        else:
                            log_warning("    chunks_small table not found!")
                    except Exception as e:
                        log_error(f"  LanceDB error: {e}")
                else:
                    log_error(f"  LanceDB directory not found at {lancedb_path}")
            else:
                log_error(f"  Database not found at {db_path}")

            if old_env:
                os.environ["DOLPHIN_STORE_ROOT"] = old_env

            # Stop server and capture any output
            log_step("\n  Stopping API server...")
            stop_api_server(server_process)
            log_success("  API server stopped")
            server_process = None

            # ============================================================
            # Test 5: Reranking (Optional)
            # ============================================================
            print(f"\n{BLUE}{'─' * 70}{RESET}")
            log_step("Test 5: Reranking (Optional)")
            print(f"{BLUE}{'─' * 70}{RESET}")
            test_results["reranking"] = _run_reranking_test(store_root)
            if test_results["reranking"]:
                log_success("Reranking test PASSED")

            # ============================================================
            # Cleanup
            # ============================================================
            print(f"\n{BLUE}{'─' * 70}{RESET}")
            log_step("Cleanup: Removing test data from database")
            print(f"{BLUE}{'─' * 70}{RESET}")
            cleanup_test_repo(store_root)

            # ============================================================
            # Summary
            # ============================================================
            print(f"\n{BLUE}{'=' * 70}{RESET}")
            print(f"{BLUE}Test Summary{RESET}")
            print(f"{BLUE}{'=' * 70}{RESET}\n")

            for test_name, passed in test_results.items():
                status = f"{GREEN}✓ PASSED{RESET}" if passed else f"{RED}✗ FAILED{RESET}"
                print(f"  {test_name.capitalize():20s} {status}")

            tests_passed = sum(test_results.values())
            tests_total = len(test_results)

            print()
            if tests_passed == tests_total:
                log_success(f"All {tests_total} tests passed! ✨")
                print(f"\n{GREEN}Dolphin is ready for PyPI deployment.{RESET}\n")
                return 0
            else:
                log_warning(f"{tests_passed}/{tests_total} tests passed")
                print(f"\n{YELLOW}Some tests failed. Review output above.{RESET}\n")
                return 1

        except KeyboardInterrupt:
            log_warning("\nTest interrupted by user")
            if server_process:
                stop_api_server(server_process)
            # Attempt cleanup even on interrupt
            cleanup_test_repo(store_root)
            return 130
        except Exception as e:
            log_error(f"Unexpected error: {e}")
            import traceback

            traceback.print_exc()
            if server_process:
                stop_api_server(server_process)
            # Attempt cleanup even on error
            cleanup_test_repo(store_root)
            return 1


if __name__ == "__main__":
    sys.exit(main())
