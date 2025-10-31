"""Pytest configuration and shared fixtures for KB pipeline tests."""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Generator
from unittest.mock import patch, MagicMock

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
    # Disable GPG signing for tests
    subprocess.run(["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"], check=True)

    return repo_path


class MockTiktokenEncoding:
    """Mock tiktoken encoding for testing without network access.

    Uses a hybrid approach: roughly 3 characters per token on average,
    similar to real tiktoken behavior, while maintaining reversibility.
    """

    def __init__(self, name: str = "cl100k_base"):
        self.name = name
        self._token_map = {}  # Maps tokens back to text
        self._next_token_id = 1000  # Start from 1000 to avoid chr() conflicts

    def encode(self, text: str) -> list[int]:
        """Encode text with ~3 chars per token average."""
        tokens = []
        i = 0
        while i < len(text):
            # Take 2-4 characters per token (avg 3)
            chunk_size = 3
            if i + chunk_size > len(text):
                chunk_size = len(text) - i

            chunk = text[i:i+chunk_size]

            # Create or retrieve token ID for this chunk
            token_id = hash(chunk) % 1000000  # Use hash for deterministic IDs
            self._token_map[token_id] = chunk
            tokens.append(token_id)

            i += chunk_size

        return tokens

    def decode(self, tokens: list[int]) -> str:
        """Decode tokens back to text."""
        result = []
        for token_id in tokens:
            if token_id in self._token_map:
                result.append(self._token_map[token_id])
            else:
                # Fallback for unknown tokens - shouldn't happen in practice
                result.append('???')
        return ''.join(result)


@pytest.fixture(scope="session", autouse=True)
def mock_tiktoken():
    """Mock tiktoken.get_encoding to avoid network calls during tests."""
    mock_encoding = MockTiktokenEncoding()

    def mock_get_encoding(encoding_name: str):
        return mock_encoding

    with patch('tiktoken.get_encoding', side_effect=mock_get_encoding):
        yield mock_encoding
