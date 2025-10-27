"""Pytest configuration and shared fixtures for KB pipeline tests."""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Generator

from tests.kb_utils import InMemoryKBBackend, FIXTURE_REPO_ROOT


@pytest.fixture(scope="session")
def sample_repo_path() -> Path:
    """Path to the sample repository fixture."""
    return FIXTURE_REPO_ROOT


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for isolated tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def temp_db_path(temp_dir: Path) -> Path:
    """Temporary database path for isolated tests."""
    return temp_dir / "test_metadata.db"


@pytest.fixture
def in_memory_backend(sample_repo_path: Path) -> InMemoryKBBackend:
    """In-memory backend for fast testing."""
    return InMemoryKBBackend(sample_repo_path)


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service for predictable tests."""
    class MockEmbeddingService:
        def __init__(self, embedding_size: int = 1536):
            self.embedding_size = embedding_size
            
        def get_embeddings(self, texts: list[str]) -> list[list[float]]:
            """Return deterministic embeddings for testing."""
            embeddings = []
            for i, text in enumerate(texts):
                # Create deterministic embedding based on text content
                embedding = [float((hash(text) + j) % 100) / 100.0 for j in range(self.embedding_size)]
                embeddings.append(embedding)
            return embeddings
            
    return MockEmbeddingService()


@pytest.fixture
def git_repo(temp_dir: Path) -> Path:
    """Create a git repository for testing."""
    import subprocess
    
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()
    
    # Initialize git repo
    subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test User"], check=True)
    
    return repo_path
