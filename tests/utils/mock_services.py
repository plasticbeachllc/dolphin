"""Mock services for predictable test results."""

from pathlib import Path
from typing import Any


class MockEmbeddingService:
    """Mock embedding service for predictable test results."""

    def __init__(self, embedding_size: int = 1536):
        self.embedding_size = embedding_size

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic embeddings for testing.

        Args:
            texts: List of text strings to embed

        Returns:
            List of deterministic embedding vectors
        """
        embeddings = []
        for i, text in enumerate(texts):
            # Create deterministic embedding based on text content and index
            embedding = [float((hash(text) + j + i) % 100) / 100.0 for j in range(self.embedding_size)]
            embeddings.append(embedding)
        return embeddings


class MockLanceDBBackend:
    """Mock LanceDB backend for testing when LanceDB is not available."""

    def __init__(self, db_path: str, **kwargs):
        self.db_path = db_path
        self.data = []

    def search(self, query: str, **kwargs) -> list[dict[str, Any]]:
        """Mock search that returns empty results."""
        return []

    def add_documents(self, documents: list[dict[str, Any]]) -> None:
        """Mock document addition."""
        self.data.extend(documents)

    def clear(self) -> None:
        """Clear mock data."""
        self.data.clear()


class MockOpenAIClient:
    """Mock OpenAI client for testing."""

    def __init__(self):
        self.embeddings = MockEmbeddingService()

    def embeddings_create(self, input: list[str], model: str) -> dict[str, Any]:
        """Mock embeddings creation."""
        embedding_data = [
            {"embedding": embedding, "index": i, "object": "embedding"}
            for i, embedding in enumerate(self.embeddings.get_embeddings(input))
        ]

        return {
            "object": "list",
            "data": embedding_data,
            "model": model,
            "usage": {
                "prompt_tokens": sum(len(text.split()) for text in input),
                "total_tokens": sum(len(text.split()) for text in input),
            },
        }


class MockGitService:
    """Mock Git service for testing repository operations."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.commits = []

    def get_latest_commit(self) -> str:
        """Return a mock commit SHA."""
        return "mock-commit-sha"

    def get_file_history(self, file_path: str) -> list[dict[str, Any]]:
        """Return mock file history."""
        return [
            {
                "commit": "mock-commit-1",
                "author": "test@example.com",
                "date": "2024-01-01T00:00:00Z",
                "message": "Initial commit",
            }
        ]

    def get_changed_files(self, since_commit: str | None = None) -> list[str]:
        """Return mock changed files."""
        return ["src/main.py", "docs/readme.md"]


class MockFileSystem:
    """Mock file system for testing file operations."""

    def __init__(self):
        self.files: dict[Path, str] = {}

    def write_file(self, path: Path, content: str) -> None:
        """Write a file to the mock filesystem."""
        self.files[path] = content

    def read_file(self, path: Path) -> str:
        """Read a file from the mock filesystem."""
        return self.files.get(path, "")

    def file_exists(self, path: Path) -> bool:
        """Check if a file exists in the mock filesystem."""
        return path in self.files

    def delete_file(self, path: Path) -> None:
        """Delete a file from the mock filesystem."""
        if path in self.files:
            del self.files[path]

    def list_files(self, directory: Path, pattern: str = "*") -> list[Path]:
        """List files in a directory."""
        return [path for path in self.files.keys() if path.parent == directory and path.match(pattern)]
