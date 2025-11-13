"""Pytest configuration and shared fixtures for KB pipeline tests."""

import shutil
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from tests.kb_utils import FIXTURE_REPO_ROOT, InMemoryKBBackend


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
def temp_db_path(temp_dir: Path) -> Generator[Path, None, None]:
    """Temporary database path for isolated tests with cleanup."""
    db_path = temp_dir / "test_metadata.db"
    yield db_path
    # Cleanup: Ensure database is closed and removed
    # The temp_dir context manager will handle file deletion


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
                embedding = [
                    float((hash(text) + j) % 100) / 100.0
                    for j in range(self.embedding_size)
                ]
                embeddings.append(embedding)
            return embeddings

    return MockEmbeddingService()


def init_test_git_repo(repo_path: Path) -> None:
    """Initialize a git repository with test-friendly defaults.

    This helper disables commit signing at the repo level (not globally)
    to avoid signing server failures in test environments.
    """
    import subprocess

    subprocess.run(
        ["git", "-C", str(repo_path), "init"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.name", "Test User"], check=True
    )
    # Disable GPG signing for this repo only (not globally)
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"], check=True
    )


@pytest.fixture
def git_repo(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a git repository for testing with proper cleanup."""
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()
    init_test_git_repo(repo_path)
    yield repo_path
    # Cleanup is handled by temp_dir context manager


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

            chunk = text[i : i + chunk_size]

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
                result.append("???")
        return "".join(result)


def validate_tiktoken_cache() -> tuple[bool, str]:
    """Validate that cached tiktoken data is usable.

    Returns (is_valid, error_message).

    Performs actual encode/decode operations to verify cache integrity:
    - Loads the encoding
    - Encodes known text
    - Verifies token count is reasonable
    - Decodes tokens back to text
    - Verifies roundtrip works
    """
    try:
        import tiktoken

        # Load the encoding
        enc = tiktoken.get_encoding("cl100k_base")

        # Test with known text - these values are stable for cl100k_base
        test_cases = [
            ("hello world", 2),  # Should be exactly 2 tokens
            ("The quick brown fox", 4),  # Should be exactly 4 tokens
        ]

        for text, expected_tokens in test_cases:
            # Encode
            tokens = enc.encode(text)

            # Verify token count is reasonable
            if len(tokens) != expected_tokens:
                return False, (
                    f"Cache validation failed: '{text}' produced {len(tokens)} tokens, "
                    f"expected {expected_tokens}. Cache may be corrupted or from wrong tiktoken version."
                )

            # Verify decode roundtrip
            decoded = enc.decode(tokens)
            if decoded != text:
                return False, (
                    f"Cache validation failed: Encode/decode roundtrip failed. "
                    f"Original: '{text}', Decoded: '{decoded}'. Cache is corrupted."
                )

        return True, ""

    except Exception as e:
        return False, f"Cache validation failed: {str(e)}"


def ensure_tiktoken_available(force_refresh: bool = False) -> bool:
    """Ensure tiktoken encoding data is available and valid.

    Args:
        force_refresh: If True, skip cache and force re-download

    Validates cached data by:
    1. Loading encoding successfully
    2. Testing encode/decode operations
    3. Verifying token counts match expected values

    Returns True if tiktoken is available and validated, False otherwise.
    """
    import os

    # Check for force refresh environment variable
    if not force_refresh:
        force_refresh = os.getenv("TIKTOKEN_FORCE_REFRESH", "").lower() in (
            "1",
            "true",
            "yes",
        )

    if force_refresh:
        # Clear cache to force re-download
        import shutil

        cache_dir = os.path.expanduser("~/.cache/tiktoken")
        if os.path.exists(cache_dir):
            print(f"Force refresh: Clearing tiktoken cache at {cache_dir}")
            shutil.rmtree(cache_dir)

    try:
        import tiktoken

        # Try to load and validate encoding
        is_valid, error_msg = validate_tiktoken_cache()

        if is_valid:
            return True
        else:
            # Cache exists but is invalid
            print(f"Warning: {error_msg}")
            return False

    except Exception as e:
        error_msg = str(e)
        # If it's a network error, data isn't cached
        if (
            "403" in error_msg
            or "Forbidden" in error_msg
            or "Failed to fetch" in error_msg
        ):
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
        "tests/integration" in str(item.fspath) for item in request.session.items
    )

    if not has_integration_tests:
        # Only unit tests - mock tiktoken is fine
        return

    # Integration tests require real tiktoken
    if ensure_tiktoken_available():
        # Tiktoken is available and validated
        return

    # Tiktoken not available or validation failed - try to download
    print("\n" + "=" * 70)
    print("Tiktoken encoding data not found or invalid. Attempting download...")
    print("=" * 70)

    try:
        import tiktoken

        print("Downloading cl100k_base encoding...", end=" ", flush=True)
        tiktoken.get_encoding("cl100k_base")
        print("✓ Downloaded!")

        # Validate the downloaded data
        print("Validating downloaded data...", end=" ", flush=True)
        is_valid, error_msg = validate_tiktoken_cache()
        if not is_valid:
            print(f"✗ Validation failed!")
            print(f"Error: {error_msg}")
            raise RuntimeError(f"Downloaded tiktoken data is invalid: {error_msg}")

        print("✓ Validated!")
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
        print(
            "Integration tests must use real tiktoken to validate production behavior."
        )
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
            print("     scp user@dev-machine:~/.cache/tiktoken/* ~/.cache/tiktoken/")
            print()
            print("  3. In production, ensure tiktoken data is pre-downloaded")
            print("     during deployment or included in container image")
        elif (
            "validation failed" in error_msg.lower() or "corrupted" in error_msg.lower()
        ):
            print(
                "Cached tiktoken data failed validation (corrupted or wrong version)."
            )
            print()
            print("Solutions:")
            print("  1. Force refresh (clears cache and re-downloads):")
            print("     TIKTOKEN_FORCE_REFRESH=1 pytest tests/integration/")
            print()
            print("  2. Manually clear cache and re-download:")
            print("     rm -rf ~/.cache/tiktoken/")
            print("     python scripts/download_tiktoken.py")
            print()
            print("  3. If problem persists, check tiktoken library version:")
            print("     pip show tiktoken")
        else:
            print(f"Unexpected error: {error_msg}")
            print()
            print("Solutions:")
            print("  1. Try force refresh:")
            print("     TIKTOKEN_FORCE_REFRESH=1 pytest tests/integration/")
            print()
            print("  2. Try manual download:")
            print("     python scripts/download_tiktoken.py")

        print()
        print("=" * 70)

        # Fail the test session
        pytest.exit(
            "Tiktoken encoding data required for integration tests", returncode=1
        )


@pytest.fixture(scope="session")
def mock_tiktoken():
    """Mock tiktoken.get_encoding to avoid network calls during unit tests.

    Note: This fixture is NOT autouse. It must be explicitly requested by tests
    or applied via pytest marks. Integration tests should use real tiktoken.
    """
    mock_encoding = MockTiktokenEncoding()

    def mock_get_encoding(encoding_name: str):
        return mock_encoding

    with patch("tiktoken.get_encoding", side_effect=mock_get_encoding):
        yield mock_encoding


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (uses mock tiktoken)"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (uses real dependencies)",
    )


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_repos():
    """Clean up any leftover test repositories from previous test runs.

    This fixture runs both before and after all tests to ensure:
    1. Clean starting state (cleans up repos from interrupted previous runs)
    2. Clean ending state (cleans up repos created during this test run)
    """

    def _cleanup():
        """Perform the actual cleanup of test repositories."""
        try:
            from pathlib import Path

            from kb.config import CONFIG_ROOT
            from kb.store.sqlite_meta import SQLiteMetadataStore

            # Check if the default database exists
            db_path = CONFIG_ROOT / "metadata.db"
            if db_path.exists():
                store = SQLiteMetadataStore(db_path)
                store.initialize()

                # Get all repos
                with store._get_connection() as conn:
                    cursor = conn.execute("SELECT id, name FROM repos")
                    repos = cursor.fetchall()

                    # Delete test repositories (those with test-related names)
                    test_repo_patterns = [
                        "test",
                        "test_repo",
                        "test-repo",
                        "repo-1",
                        "repo-2",
                        "my-repo",
                        "integration-test",
                    ]
                    for repo_id, repo_name in repos:
                        if any(
                            pattern in repo_name.lower()
                            for pattern in test_repo_patterns
                        ):
                            # Delete all data associated with this test repo
                            conn.execute(
                                "DELETE FROM chunks WHERE repo_id = ?", (repo_id,)
                            )
                            conn.execute(
                                "DELETE FROM files WHERE repo_id = ?", (repo_id,)
                            )
                            conn.execute(
                                "DELETE FROM scan_sessions WHERE repo_id = ?",
                                (repo_id,),
                            )
                            conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))

                    conn.commit()
        except Exception:
            # Silently ignore cleanup failures - they shouldn't break tests
            pass

    # Clean up before tests (in case previous run was interrupted)
    _cleanup()

    yield

    # Clean up after all tests complete
    _cleanup()


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


# ============================================================================
# KB Auto-Sync Specific Fixtures
# ============================================================================


@pytest.fixture
def mock_kb_stores(temp_db_path):
    """Mock KB stores (SQLite + LanceDB) for testing."""
    from unittest.mock import MagicMock

    from kb.store.sqlite_meta import SQLiteMetadataStore

    # Create real SQLite store for metadata
    sql_store = SQLiteMetadataStore(temp_db_path)
    sql_store.initialize()

    # Mock LanceDB store (we don't need real vector ops for most tests)
    lance_store = MagicMock()
    lance_store.get_table.return_value = MagicMock()

    yield sql_store, lance_store

    # Cleanup - no explicit close method needed, db connections are auto-closed


@pytest.fixture
def registered_test_repo(mock_kb_stores, temp_dir):
    """Create a registered test repository."""
    from kb.api.app import set_stores

    sql_store, lance_store = mock_kb_stores
    set_stores(sql_store, lance_store)

    # Create test workspace
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir()

    # Register repo
    sql_store.record_repo(
        name="test-repo", path=workspace_path, default_embed_model="large"
    )

    # Get repo info
    repo = sql_store.get_repo_by_name("test-repo")

    yield {
        "repo_id": repo["id"],
        "name": "test-repo",  # name not returned by get_repo_by_name
        "path": str(workspace_path),
        "workspace": workspace_path,
    }

    # Cleanup handled by fixtures


@pytest.fixture
def kb_api_client(mock_kb_stores):
    """FastAPI TestClient with mocked stores."""
    from fastapi.testclient import TestClient

    from kb.api.app import app, reset_stores, set_stores

    sql_store, lance_store = mock_kb_stores
    set_stores(sql_store, lance_store)

    client = TestClient(app)
    yield client

    reset_stores()


@pytest.fixture
def mock_pipeline():
    """Mock KB pipeline for testing indexing without real embedding calls."""
    from unittest.mock import AsyncMock, MagicMock

    pipeline = MagicMock()

    # Mock process_repo to return fake results
    async def mock_process_repo(repo_path, file_paths=None, incremental=False):
        return {
            "indexed": len(file_paths) if file_paths else 0,
            "skipped": 0,
            "errors": [],
        }

    pipeline.process_repo = AsyncMock(side_effect=mock_process_repo)

    return pipeline


@pytest.fixture
def task_queue_instance():
    """Fresh TaskQueue instance for testing."""
    from kb.api.task_queue import TaskQueue

    queue = TaskQueue()
    yield queue

    # Cleanup - clear all tasks
    queue.tasks.clear()


# ============================================================================
# E2E Live Test Fixtures
# ============================================================================


@pytest.fixture
def store_root(temp_dir: Path) -> Path:
    """Temporary store root for E2E live tests."""
    store_path = temp_dir / "dolphin_store"
    store_path.mkdir(parents=True, exist_ok=True)
    return store_path


@pytest.fixture
def repo_path(temp_dir: Path) -> Path:
    """Create a test repository for E2E live tests."""
    import subprocess

    repo_dir = temp_dir / "test_repo"
    repo_dir.mkdir()

    # Create simple Python file
    (repo_dir / "main.py").write_text(
        """
def calculate_sum(numbers):
    return sum(numbers)

class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=repo_dir, check=True
    )
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


@pytest.fixture
def port() -> int:
    """Find a free port for testing."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        return s.getsockname()[1]
