"""Additional fixtures for integration tests."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def large_repo_fixture(tmp_path_factory) -> Path:
    """Create a larger repository fixture for performance testing."""
    repo_path = tmp_path_factory.mktemp("large_repo")

    # Create multiple files with various content types
    file_structure = [
        (
            "src/main.py",
            """
import os
import sys

class MainApplication:
    def __init__(self):
        self.config = {}
    
    def run(self):
        print("Running application")
        return True

if __name__ == "__main__":
    app = MainApplication()
    app.run()
""",
        ),
        (
            "src/utils.py",
            """
import json
from typing import Dict, Any

def load_config(path: str) -> Dict[str, Any]:
    with open(path, 'r') as f:
        return json.load(f)

def save_config(config: Dict[str, Any], path: str) -> None:
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
""",
        ),
        (
            "docs/architecture.md",
            """
# System Architecture

## Overview
This document describes the system architecture.

## Components
- **Main Application**: Handles core functionality
- **Utils**: Utility functions for configuration
- **API**: REST API endpoints

## Design Patterns
We use the following design patterns:
- Factory Pattern
- Singleton Pattern
- Observer Pattern
""",
        ),
        (
            "tests/test_main.py",
            """
import pytest
from src.main import MainApplication

class TestMainApplication:
    def test_initialization(self):
        app = MainApplication()
        assert app.config == {}
    
    def test_run_method(self):
        app = MainApplication()
        result = app.run()
        assert result is True
""",
        ),
        (
            "config/settings.json",
            """
{
  "database": {
    "host": "localhost",
    "port": 5432
  },
  "api": {
    "port": 8000,
    "debug": true
  }
}
""",
        ),
        (
            "README.md",
            """
# Test Repository

This is a larger test repository for integration testing.

## Features
- Multiple file types
- Various programming languages
- Comprehensive test coverage
""",
        ),
    ]

    # Create the file structure
    for file_path, content in file_structure:
        full_path = repo_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content.strip())

    return repo_path


@pytest.fixture(scope="session")
def malformed_repo_fixture(tmp_path_factory) -> Path:
    """Create a repository with malformed files for error handling testing."""
    repo_path = tmp_path_factory.mktemp("malformed_repo")

    # Create files with various issues
    problematic_files = [
        (
            "broken.py",
            """
def broken_function(
    missing_paren:
    pass

class BrokenClass
    def method(self):
        return
""",
        ),
        ("empty.py", ""),
        ("huge_binary.bin", b"\x00" * 1024),  # 1KB of null bytes
        ("weird_encoding.txt", "Normal text with some \x00 null bytes"),
        ("nested/deeply/nested/file.py", "print('deeply nested')"),
        ("symlink_target.py", "# Target of symlink"),
    ]

    # Create the problematic files
    for file_path, content in problematic_files:
        full_path = repo_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            full_path.write_bytes(content)
        else:
            full_path.write_text(content)

    # Create a symlink (if supported)
    try:
        symlink_path = repo_path / "symlink.py"
        target_path = repo_path / "symlink_target.py"
        symlink_path.symlink_to(target_path)
    except (OSError, NotImplementedError):
        # Symlinks not supported on this platform
        pass

    return repo_path


@pytest.fixture
def integration_backend_config(
    sample_repo_path: Path, temp_db_path: Path, mock_embedding_service, temp_dir: Path
):
    """Provide a complete backend configuration for integration testing with isolated storage."""
    from kb.config import KBConfig
    from kb.store import LanceDBStore, SQLiteMetadataStore

    # Use temp_dir to ensure isolated storage for each test
    store_root = temp_dir / "kb_store"
    store_root.mkdir(parents=True, exist_ok=True)

    config = KBConfig(
        store_root=store_root,
        default_embed_model="small",
        ignore=["*.pyc", "__pycache__/*", "*.bin"],
        max_file_size=1024 * 1024,  # 1MB
        chunk_size=1000,
        chunk_overlap=200,
    )

    # Use isolated database and vector store paths
    metadata_store = SQLiteMetadataStore(temp_db_path)
    metadata_store.initialize()

    # Use a unique in-memory LanceDB instance for each test (faster than disk)
    import uuid

    lancedb_store = LanceDBStore(f"memory://integration_test_{uuid.uuid4().hex}")

    backend_config = {
        "config": config,
        "metadata_store": metadata_store,
        "lancedb_store": lancedb_store,
        "repo_path": sample_repo_path,
        "embedding_service": mock_embedding_service,
    }

    yield backend_config

    # Cleanup: Close connections
    try:
        metadata_store.close()
    except Exception:
        pass


@pytest.fixture
def fast_backend_config(
    sample_repo_path: Path, temp_db_path: Path, mock_embedding_service, temp_dir: Path
):
    """Fast backend config for tests that don't need full isolation.

    This fixture is optimized for speed by:
    - Using in-memory SQLite database
    - Using in-memory LanceDB
    - Minimal initialization
    """
    import uuid

    from kb.config import KBConfig
    from kb.store import LanceDBStore, SQLiteMetadataStore

    config = KBConfig(
        default_embed_model="small",
        ignore=["*.pyc", "__pycache__/*", "*.bin"],
        max_file_size=1024 * 1024,
        chunk_size=1000,
        chunk_overlap=200,
    )

    # Use in-memory database for faster tests
    metadata_store = SQLiteMetadataStore(":memory:")
    metadata_store.initialize()

    # Use in-memory LanceDB for speed
    lancedb_store = LanceDBStore(f"memory://fast_test_{uuid.uuid4().hex}")

    backend_config = {
        "config": config,
        "metadata_store": metadata_store,
        "lancedb_store": lancedb_store,
        "repo_path": sample_repo_path,
        "embedding_service": mock_embedding_service,
    }

    yield backend_config

    try:
        metadata_store.close()
    except Exception:
        pass


@pytest.fixture
def registered_test_repo(integration_backend_config):
    """Register a test repository in the metadata store with cleanup."""
    metadata_store = integration_backend_config["metadata_store"]
    repo_path = integration_backend_config["repo_path"]

    # Initialize the metadata store to ensure tables exist
    metadata_store.initialize()

    metadata_store.record_repo(
        name="integration-test-repo", path=repo_path, default_embed_model="small"
    )
    repo = metadata_store.get_repo_by_name("integration-test-repo")
    repo_id = int(repo["id"]) if repo else 0

    repo_data = {
        "repo_id": repo_id,
        "repo_name": "integration-test-repo",
        "repo_path": repo_path,
    }

    yield repo_data

    # Cleanup: Remove the test repository from the database
    try:
        # Delete all data associated with this repo
        if repo_id:
            with metadata_store._get_connection() as conn:
                # Delete in order to respect foreign key constraints
                conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
                conn.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
                conn.execute("DELETE FROM scan_sessions WHERE repo_id = ?", (repo_id,))
                conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
                conn.commit()
    except Exception as e:
        # Log cleanup failures but don't fail the test
        import logging

        logging.warning(f"Failed to cleanup test repo {repo_id}: {e}")


@pytest.fixture
def pipeline_with_registered_repo(integration_backend_config, registered_test_repo):
    """Create an ingestion pipeline with a pre-registered repository."""
    from kb.ingest.pipeline import IngestionPipeline

    pipeline = IngestionPipeline(
        config=integration_backend_config["config"],
        lancedb=integration_backend_config["lancedb_store"],
        metadata=integration_backend_config["metadata_store"],
    )

    return {
        "pipeline": pipeline,
        "repo_name": registered_test_repo["repo_name"],
        "repo_path": registered_test_repo["repo_path"],
    }


@pytest.fixture(scope="session")
def performance_test_data(tmp_path_factory) -> Path:
    """Create performance test data with many small files."""
    repo_path = tmp_path_factory.mktemp("performance_repo")

    # Create many small Python files
    for i in range(100):
        file_path = repo_path / f"src/module_{i:03d}.py"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = f"""
# Module {i}

def function_{i}():
    return {i}

class Class{i}:
    def method_{i}(self):
        return "result_{i}"
"""
        file_path.write_text(content.strip())

    # Create some larger files
    large_file = repo_path / "src/large_module.py"
    large_content = "# Large module\n" + "\n".join(
        [f"def large_function_{i}():\n    return {i}" for i in range(500)]
    )
    large_file.write_text(large_content)

    return repo_path


@pytest.fixture(scope="session", autouse=True)
def ensure_fixture_repo_is_git(sample_repo_path: Path) -> Path:
    """Ensure the shared sample_repo_path is a Git repo for scan/index tests."""
    import subprocess

    git_dir = sample_repo_path / ".git"
    if not git_dir.exists():
        try:
            subprocess.run(
                ["git", "init"], cwd=sample_repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=sample_repo_path,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=sample_repo_path,
                check=True,
            )
            # Disable GPG signing for this repo only (not globally)
            subprocess.run(
                ["git", "config", "commit.gpgsign", "false"],
                cwd=sample_repo_path,
                check=True,
            )
            subprocess.run(
                ["git", "add", "."],
                cwd=sample_repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=sample_repo_path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # If git is not available, allow tests that rely on Git to fail or be skipped
            pass
    return sample_repo_path
