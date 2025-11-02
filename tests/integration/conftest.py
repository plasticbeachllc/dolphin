"""Additional fixtures for integration tests."""

import pytest
from pathlib import Path
from typing import Generator


@pytest.fixture(scope="session")
def large_repo_fixture(tmp_path_factory) -> Path:
    """Create a larger repository fixture for performance testing."""
    repo_path = tmp_path_factory.mktemp("large_repo")
    
    # Create multiple files with various content types
    file_structure = [
        ("src/main.py", """
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
"""),
        ("src/utils.py", """
import json
from typing import Dict, Any

def load_config(path: str) -> Dict[str, Any]:
    with open(path, 'r') as f:
        return json.load(f)

def save_config(config: Dict[str, Any], path: str) -> None:
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
"""),
        ("docs/architecture.md", """
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
"""),
        ("tests/test_main.py", """
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
"""),
        ("config/settings.json", """
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
"""),
        ("README.md", """
# Test Repository

This is a larger test repository for integration testing.

## Features
- Multiple file types
- Various programming languages
- Comprehensive test coverage
""")
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
        ("broken.py", """
def broken_function(
    missing_paren:
    pass

class BrokenClass
    def method(self):
        return
"""),
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
    sample_repo_path: Path,
    temp_db_path: Path,
    mock_embedding_service
):
    """Provide a complete backend configuration for integration testing."""
    from kb.config import KBConfig
    from kb.store import LanceDBStore, SQLiteMetadataStore
    
    config = KBConfig(
        default_embed_model="small",
        ignore=["*.pyc", "__pycache__/*", "*.bin"],
        max_file_size=1024 * 1024,  # 1MB
        chunk_size=1000,
        chunk_overlap=200
    )
    
    metadata_store = SQLiteMetadataStore(temp_db_path)
    lancedb_store = LanceDBStore("memory://integration_test_db")
    
    return {
        "config": config,
        "metadata_store": metadata_store,
        "lancedb_store": lancedb_store,
        "repo_path": sample_repo_path,
        "embedding_service": mock_embedding_service
    }


@pytest.fixture
def registered_test_repo(integration_backend_config):
    """Register a test repository in the metadata store."""
    metadata_store = integration_backend_config["metadata_store"]
    repo_path = integration_backend_config["repo_path"]
    
    metadata_store.record_repo(
        name="integration-test-repo",
        path=repo_path,
        default_embed_model="small"
    )
    repo = metadata_store.get_repo_by_name("integration-test-repo")
    repo_id = int(repo["id"]) if repo else 0
    
    return {
        "repo_id": repo_id,
        "repo_name": "integration-test-repo",
        "repo_path": repo_path
    }


@pytest.fixture
def pipeline_with_registered_repo(integration_backend_config, registered_test_repo):
    """Create an ingestion pipeline with a pre-registered repository."""
    from kb.ingest.pipeline import IngestionPipeline
    
    pipeline = IngestionPipeline(
        config=integration_backend_config["config"],
        lancedb=integration_backend_config["lancedb_store"],
        metadata=integration_backend_config["metadata_store"]
    )
    
    return {
        "pipeline": pipeline,
        "repo_name": registered_test_repo["repo_name"],
        "repo_path": registered_test_repo["repo_path"]
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
    large_content = "# Large module\n" + "\n".join([
        f"def large_function_{i}():\n    return {i}" 
        for i in range(500)
    ])
    large_file.write_text(large_content)
    
    return repo_path


@pytest.fixture(scope="session", autouse=True)
def ensure_fixture_repo_is_git(sample_repo_path: Path) -> Path:
    """Ensure the shared sample_repo_path is a Git repo for scan/index tests."""
    import subprocess

    git_dir = sample_repo_path / ".git"
    if not git_dir.exists():
        try:
            subprocess.run(["git", "init"], cwd=sample_repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=sample_repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=sample_repo_path, check=True)
            # Disable GPG signing for this repo only (not globally)
            subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=sample_repo_path, check=True)
            subprocess.run(["git", "add", "."], cwd=sample_repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=sample_repo_path, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # If git is not available, allow tests that rely on Git to fail or be skipped
            pass
    return sample_repo_path