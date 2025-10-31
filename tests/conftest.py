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


def init_test_git_repo(repo_path: Path) -> None:
    """Initialize a git repository with test-friendly defaults.

    This helper disables commit signing at the repo level (not globally)
    to avoid signing server failures in test environments.
    """
    import subprocess

    subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test User"], check=True)
    # Disable GPG signing for this repo only (not globally)
    subprocess.run(["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"], check=True)


@pytest.fixture
def git_repo(temp_dir: Path) -> Path:
    """Create a git repository for testing."""
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()
    init_test_git_repo(repo_path)
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


def ensure_tiktoken_available() -> bool:
    """Ensure tiktoken encoding data is available.

    Tries to:
    1. Use existing cached tiktoken data
    2. Download tiktoken data if cache missing

    Returns True if tiktoken is available, False otherwise.
    """
    try:
        import tiktoken
        # Try to load encoding - will use cache if available
        tiktoken.get_encoding("cl100k_base")
        return True
    except Exception as e:
        error_msg = str(e)
        # If it's a network error, data isn't cached
        if "403" in error_msg or "Forbidden" in error_msg or "Failed to fetch" in error_msg:
            return False
        # Other errors might be real issues
        return False


@pytest.fixture(scope="session", autouse=True)
def setup_tiktoken(request):
    """Ensure tiktoken is available for integration tests.

    This runs once at the start of the test session and:
    1. Checks if integration tests are being run
    2. If yes, ensures tiktoken data is available (cached or downloads)
    3. If download fails and no cache, fails the test session

    Unit tests use mock tiktoken (fast, testing logic).
    Integration tests require real tiktoken (production validation).
    """
    # Check if any integration tests are being run
    has_integration_tests = any(
        "tests/integration" in str(item.fspath)
        for item in request.session.items
    )

    if not has_integration_tests:
        # Only unit tests - mock tiktoken is fine
        return

    # Integration tests require real tiktoken
    if ensure_tiktoken_available():
        # Tiktoken is available (either cached or just downloaded)
        return

    # Try to download
    print("\n" + "=" * 70)
    print("Tiktoken encoding data not found. Attempting download...")
    print("=" * 70)

    try:
        import tiktoken
        print("Downloading cl100k_base encoding...", end=" ", flush=True)
        tiktoken.get_encoding("cl100k_base")
        print("✓ Success!")
        print("=" * 70)
        return
    except Exception as e:
        error_msg = str(e)
        print(f"✗ Failed: {error_msg[:100]}")
        print("=" * 70)
        print()
        print("❌ ERROR: Integration tests require tiktoken encoding data")
        print()
        print("Production requires real tiktoken (OpenAI's tokenizer).")
        print("Integration tests must use real tiktoken to validate production behavior.")
        print()
        print("Unit tests can run offline (use mock tiktoken):")
        print("  pytest tests/unit/")
        print()

        if "403" in error_msg or "Forbidden" in error_msg:
            print("Network access to OpenAI's blob storage is blocked.")
            print()
            print("Solutions:")
            print("  1. Run from an environment with network access:")
            print("     python scripts/download_tiktoken.py")
            print()
            print("  2. Copy cached data from another machine:")
            print("     scp user@other-machine:~/.cache/tiktoken/* ~/.cache/tiktoken/")
            print()
            print("  3. In production, ensure tiktoken data is pre-downloaded")
            print("     during deployment or included in container image")
        else:
            print(f"Unexpected error: {error_msg}")
            print()
            print("Try running: python scripts/download_tiktoken.py")

        print()
        print("=" * 70)

        # Fail the test session
        pytest.exit("Tiktoken encoding data required for integration tests", returncode=1)


@pytest.fixture(scope="session")
def mock_tiktoken():
    """Mock tiktoken.get_encoding to avoid network calls during unit tests.

    Note: This fixture is NOT autouse. It must be explicitly requested by tests
    or applied via pytest marks. Integration tests should use real tiktoken.
    """
    mock_encoding = MockTiktokenEncoding()

    def mock_get_encoding(encoding_name: str):
        return mock_encoding

    with patch('tiktoken.get_encoding', side_effect=mock_get_encoding):
        yield mock_encoding


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (uses mock tiktoken)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (uses real dependencies)"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically apply mock_tiktoken fixture to unit tests only.

    Unit tests use mock tiktoken for speed and to test logic in isolation.
    Integration tests use real tiktoken to validate production behavior.
    """
    for item in items:
        # Check if test is in unit test directory
        if "tests/unit" in str(item.fspath):
            # Unit tests use mock for speed (testing logic, not tokenization accuracy)
            if "mock_tiktoken" not in item.fixturenames:
                item.fixturenames.append("mock_tiktoken")
            item.add_marker(pytest.mark.unit)
        elif "tests/integration" in str(item.fspath):
            # Integration tests use real tiktoken (validated by setup_tiktoken fixture)
            item.add_marker(pytest.mark.integration)
