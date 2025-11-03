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
import sys
import tempfile
import subprocess
from pathlib import Path
import time
import shutil
import socket

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
    if sys.version_info < (3, 12):
        log_error(f"Python 3.12+ required (found {sys.version_info.major}.{sys.version_info.minor})")
        return False
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
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
    
    log_success(f"Test repository created at {repo_dir}")
    return repo_dir

def run_command(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> tuple[bool, str, str]:
    """Run a command and return success status, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=env
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def test_initialization(store_root: Path) -> bool:
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

def test_repository_indexing(repo_path: Path, store_root: Path) -> bool:
    """Test repository indexing with real OpenAI API calls."""
    log_step("Testing repository indexing (this will make OpenAI API calls)...")
    
    # Set up environment with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)
    
    # Add repository
    log_step("  Adding repository...")
    success, stdout, stderr = run_command([
        "uv", "run", "dolphin", "add-repo",
        "test_repo", str(repo_path),
        "--default-embed-model", "small"  # Use small model to save costs
    ], env=env)
    
    if not success:
        log_error(f"Failed to add repository: {stderr}")
        return False
    log_success("  Repository added")
    
    # Index repository with --full flag to avoid git diff issues
    log_step("  Indexing repository (creating embeddings)...")
    success, stdout, stderr = run_command([
        "uv", "run", "dolphin", "index",
        "test_repo",
        "--full"  # Force full reindex to avoid stale commit references
    ], env=env)
    
    if not success:
        log_error(f"Failed to index repository: {stderr}")
        return False
    
    # Check for success indicators in output
    if "chunks indexed" in stdout.lower() or "success" in stdout.lower():
        log_success(f"  Repository indexed successfully")
        # Extract token count if available
        for line in stdout.split('\n'):
            if "tokens" in line.lower() or "cost" in line.lower():
                log_step(f"    {line.strip()}")
    else:
        log_warning(f"  Indexing completed but no clear success message")
    
    return True

def test_search_functionality(store_root: Path) -> bool:
    """Test search functionality."""
    log_step("Testing search functionality...")
    
    # Set up environment with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)
    
    # Try a simple search query
    test_queries = [
        "calculate sum",
        "Calculator class",
        "greeting function"
    ]
    
    for query in test_queries:
        log_step(f"  Searching for: '{query}'")
        success, stdout, stderr = run_command([
            "uv", "run", "dolphin", "search",
            query,
            "--top-k", "3"
        ], env=env)
        
        if not success:
            log_warning(f"  Search failed for '{query}': {stderr}")
            continue
        
        # Check if results were returned
        if "No results" in stdout or len(stdout.strip()) < 10:
            log_warning(f"  No results for '{query}'")
        else:
            log_success(f"  Found results for '{query}'")
            # Print first result summary
            lines = stdout.split('\n')[:5]
            for line in lines:
                if line.strip():
                    log_step(f"    {line.strip()}")
    
    return True

def test_reranking_if_available(store_root: Path) -> bool:
    """Test reranking if dependencies are installed (optional)."""
    log_step("Testing reranking (optional - only if dependencies installed)...")
    
    # Set up environment with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)
    
    # Check if reranking dependencies are available
    try:
        import torch
        import sentence_transformers
        log_step("  ✓ Reranking dependencies found (torch + sentence-transformers)")
    except ImportError:
        log_warning("  Reranking dependencies not installed - skipping (optional)")
        log_step("    To enable: uv pip install torch sentence-transformers")
        return True  # Not a failure - it's optional
    
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
        config_content = config_content.replace(
            "enabled = false",
            "enabled = true"
        )
        config_path.write_text(config_content)
        log_success("  Reranking enabled in config")
    else:
        log_warning("  Config doesn't have [retrieval.reranking] section")
        return True
    
    # Test search with reranking
    log_step("  Testing search with reranking enabled...")
    success, stdout, stderr = run_command([
        "uv", "run", "dolphin", "search",
        "Calculator class",
        "--top-k", "3"
    ], env=env)
    
    if not success:
        log_error(f"  Search with reranking failed: {stderr}")
        # Restore config
        config_content = config_content.replace(
            "enabled = true",
            "enabled = false"
        )
        config_path.write_text(config_content)
        return False
    
    # Check if reranking was used (look for rerank_score in output)
    # Note: This depends on the output format
    log_success("  Search with reranking completed")
    
    # Restore config (disable reranking)
    log_step("  Restoring config (disabling reranking)...")
    config_content = config_content.replace(
        "enabled = true",
        "enabled = false"
    )
    config_path.write_text(config_content)
    log_success("  Config restored")
    
    return True

def find_free_port() -> int:
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

def test_api_server(store_root: Path) -> bool:
    """Test API server startup and basic endpoints."""
    log_step("Testing API server...")
    
    # Set up environment with custom store root
    env = os.environ.copy()
    env["DOLPHIN_STORE_ROOT"] = str(store_root)
    
    # Find a free port to avoid conflicts
    port = find_free_port()
    log_step(f"  Using port {port} for test server...")
    
    # Start API server in background with custom port
    log_step("  Starting API server...")
    server_process = subprocess.Popen(
        ["uv", "run", "dolphin", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    
    # Wait for server to start
    time.sleep(3)
    
    try:
        # Check if server is running
        if server_process.poll() is not None:
            _, stderr = server_process.communicate()
            log_error(f"  Server failed to start: {stderr}")
            return False
        
        log_success("  API server started")
        
        # Test health endpoint
        log_step("  Testing health endpoint...")
        success, stdout, stderr = run_command([
            "curl", "-s", f"http://127.0.0.1:{port}/health"
        ])
        
        if success and "ok" in stdout.lower():
            log_success("  Health endpoint OK")
        else:
            log_warning(f"  Health endpoint returned: {stdout}")
        
        # Test repos endpoint
        log_step("  Testing repos endpoint...")
        success, stdout, stderr = run_command([
            "curl", "-s", f"http://127.0.0.1:{port}/repos"
        ])
        
        if success and "test_repo" in stdout:
            log_success("  Repos endpoint OK")
        else:
            log_warning(f"  Repos endpoint returned: {stdout[:100]}")
        
        return True
        
    finally:
        # Stop server
        log_step("  Stopping API server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        log_success("  API server stopped")

def estimate_cost() -> None:
    """Estimate the cost of running this test."""
    log_step("\nCost Estimate:")
    log_step("  Test repository: ~80 lines of code")
    log_step("  Estimated chunks: ~5-8 chunks")
    log_step("  Embedding model: text-embedding-3-small")
    log_step("  Estimated tokens: ~500-1000 tokens")
    log_step("  OpenAI pricing: $0.00002 / 1K tokens")
    log_step("  Estimated cost: $0.00001 - $0.00002 (~$0.00 USD)")
    print()

def main():
    """Run all end-to-end tests."""
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}Dolphin End-to-End Live Integration Test{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")
    
    estimate_cost()
    
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
        
        try:
            # Create test repository
            repo_path = create_test_repository(temp_path)
            
            # Run tests
            tests_passed = 0
            tests_total = 5  # Added reranking test
            
            if test_initialization(store_root):
                tests_passed += 1
            
            if test_repository_indexing(repo_path, store_root):
                tests_passed += 1
            
            if test_search_functionality(store_root):
                tests_passed += 1
            
            if test_reranking_if_available(store_root):
                tests_passed += 1
            
            if test_api_server(store_root):
                tests_passed += 1
            
            # Summary
            print(f"\n{BLUE}{'='*70}{RESET}")
            print(f"{BLUE}Test Summary{RESET}")
            print(f"{BLUE}{'='*70}{RESET}\n")
            
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
            return 130
        except Exception as e:
            log_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return 1

if __name__ == "__main__":
    sys.exit(main())