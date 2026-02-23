"""Pytest configuration and shared fixtures for KB pipeline tests."""

import os
import shutil
import subprocess
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from kb.store.sqlite_meta import SQLiteMetadataStore
    from tests.kb_utils import InMemoryKBBackend

_TEST_CONFIG_ENV = "DOLPHIN_CONFIG_PATH"
# Keep tests deterministic by avoiding user-level configs.
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER") or "main"
_test_config_dir = Path(tempfile.mkdtemp(prefix=f"dolphin-test-config-{_xdist_worker}-"))
_test_config_path = _test_config_dir / "config.toml"
_test_config_path.write_text(
    """
[storage]
store_root = "/tmp/dolphin-test-store-{worker}"

[server]
endpoint = "127.0.0.1:7777"

[embedding]
provider = "stub"
default_embed_model = "small"

[retrieval]
score_cutoff = 0.005
top_k = 8
max_snippet_tokens = 240
mmr_enabled = true
mmr_lambda = 0.7
""".lstrip().format(worker=_xdist_worker),
    encoding="utf-8",
)
os.environ[_TEST_CONFIG_ENV] = str(_test_config_path)


@pytest.fixture(scope="session")
def sample_repo_path() -> Path:
    """Path to the sample repository fixture."""
    from tests.kb_utils import FIXTURE_REPO_ROOT

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
def in_memory_backend(sample_repo_path: Path) -> "InMemoryKBBackend":
    """In-memory backend for fast testing."""
    from tests.kb_utils import InMemoryKBBackend

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


@pytest.fixture(autouse=True, scope="session")
def _disable_retry_sleeps_for_tests() -> Generator[None, None, None]:
    """Avoid real sleeps from retry/backoff logic during tests."""
    import kb.ingest.error_logging as error_logging

    mp = pytest.MonkeyPatch()
    mp.setattr(error_logging, "_sleep", lambda _seconds: None)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture(autouse=True)
def _reset_embedding_provider_after_test() -> Generator[None, None, None]:
    """Ensure embedding provider changes do not leak across tests."""
    yield
    from kb.embeddings.provider import EmbeddingProvider, set_default_provider

    set_default_provider(EmbeddingProvider())


def init_test_git_repo(repo_path: Path) -> None:
    """Initialize a git repository with test-friendly defaults.

    This helper disables commit signing at the repo level (not globally)
    to avoid signing server failures in test environments.
    """
    import subprocess

    subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test User"], check=True)
    # Disable GPG signing for this repo only (not globally)
    subprocess.run(["git", "-C", str(repo_path), "config", "commit.gpgsign", "false"], check=True)
    # Create initial commit so HEAD is valid
    subprocess.run(["git", "-C", str(repo_path), "commit", "--allow-empty", "-m", "Initial commit"], check=True)


@pytest.fixture(scope="session")
def _git_template_dir(tmp_path_factory) -> Path:
    """Create a template git repo once per session.

    This optimization avoids running `git init` and `git config` (subprocess calls)
    for every single test that needs a repo, reducing overhead significantly.
    """
    # Create valid path for template
    template_dir = tmp_path_factory.mktemp("git_template")
    # Initialize the repo in this persistent temp dir
    init_test_git_repo(template_dir)
    return template_dir


@pytest.fixture
def git_repo(temp_dir: Path, _git_template_dir: Path) -> Generator[Path, None, None]:
    """Create a git repository for testing with proper cleanup.

    Implementation: Copies a pre-initialized template repo to the test's
    temp dir instead of running slow git commands.
    """
    repo_path = temp_dir / "test_repo"
    # Copy from template is drastically faster than subprocess git calls
    shutil.copytree(_git_template_dir, repo_path, dirs_exist_ok=True)
    yield repo_path
    # Cleanup is handled by temp_dir context manager


@pytest.fixture
def make_git_repo(_git_template_dir: Path, tmp_path: Path):
    """Factory fixture for creating git repos with custom file content.

    Usage:
        repo = make_git_repo({"main.py": "def foo(): pass"})
        empty = make_git_repo()  # empty repo with initial commit

    Built on _git_template_dir for speed (no subprocess git init).
    """
    _counter = 0

    def _factory(files: dict[str, str] | None = None, name: str = "repo") -> Path:
        nonlocal _counter
        repo_path = tmp_path / f"{name}_{_counter}"
        _counter += 1
        shutil.copytree(_git_template_dir, repo_path, dirs_exist_ok=True)

        if files:
            for relpath, content in files.items():
                fpath = repo_path / relpath
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content)
            subprocess.run(
                ["git", "-C", str(repo_path), "add", "."],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repo_path), "commit", "-m", "Add test files"],
                check=True,
                capture_output=True,
            )

        return repo_path

    return _factory


@dataclass
class KBTestEnv:
    """Fully isolated knowledge store environment for one test.

    CLI commands that call load_config() will resolve to this isolated
    store via DOLPHIN_CONFIG_PATH, preventing cross-test pollution.
    """

    config_path: Path
    store_root: Path
    metadata: "SQLiteMetadataStore"


@pytest.fixture
def isolated_kb_env(tmp_path: Path, monkeypatch) -> KBTestEnv:
    """Per-test isolated config + database.

    Creates a config.toml with isolated store_root, sets DOLPHIN_CONFIG_PATH
    via monkeypatch, and initializes a fresh SQLite metadata store.
    """
    from kb.store.sqlite_meta import SQLiteMetadataStore

    store_root = tmp_path / "kb_store"
    store_root.mkdir()

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'[storage]\nstore_root = "{store_root}"\n\n[embedding]\nprovider = "stub"\ndefault_embed_model = "small"\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("DOLPHIN_CONFIG_PATH", str(config_path))

    metadata = SQLiteMetadataStore(store_root / "metadata.db")
    metadata.initialize()

    return KBTestEnv(config_path=config_path, store_root=store_root, metadata=metadata)


@pytest.fixture
def cli_repo(git_repo: Path, isolated_kb_env: KBTestEnv):
    """Git repo registered in an isolated KB environment.

    Combines git_repo + isolated_kb_env. The repo is registered directly
    via metadata store (fast, no CLI roundtrip).
    """
    isolated_kb_env.metadata.record_repo(
        name="test-repo",
        path=git_repo,
        default_embed_model="small",
    )
    return {"repo_path": git_repo, "repo_name": "test-repo", "env": isolated_kb_env}


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
    has_integration_tests = any("tests/integration" in str(item.fspath) for item in request.session.items)

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
            print("✗ Validation failed!")
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
            print("     scp user@dev-machine:~/.cache/tiktoken/* ~/.cache/tiktoken/")
            print()
            print("  3. In production, ensure tiktoken data is pre-downloaded")
            print("     during deployment or included in container image")
        elif "validation failed" in error_msg.lower() or "corrupted" in error_msg.lower():
            print("Cached tiktoken data failed validation (corrupted or wrong version).")
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
        pytest.exit("Tiktoken encoding data required for integration tests", returncode=1)


@pytest.fixture
def mock_tiktoken():
    """Mock tiktoken.get_encoding to avoid network calls during unit tests.

    Note: This fixture is NOT autouse. It must be explicitly requested by tests
    or applied via pytest marks. Integration tests should use real tiktoken.

    Function-scoped so the patch does not leak into integration tests
    when both run on the same xdist worker.
    """
    mock_encoding = MockTiktokenEncoding()

    def mock_get_encoding(encoding_name: str):
        return mock_encoding

    with patch("tiktoken.get_encoding", side_effect=mock_get_encoding):
        yield mock_encoding


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test (uses mock tiktoken)")
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (uses real dependencies)",
    )
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")


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
            from kb.config import CONFIG_ROOT
            from kb.store.sqlite_meta import SQLiteMetadataStore

            # Check if the default database exists
            db_path = CONFIG_ROOT / "metadata.db"
            if db_path.exists():
                store = SQLiteMetadataStore(db_path)
                store.initialize()

                # Get all repos
                with store._get_connection() as conn:  # type: ignore[attr-defined]
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
                        if any(pattern in repo_name.lower() for pattern in test_repo_patterns):
                            # Delete all data associated with this test repo
                            conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
                            conn.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
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
    sql_store.record_repo(name="test-repo", path=workspace_path, default_embed_model="small")

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
def kb_api_client(mock_kb_stores, monkeypatch):
    """FastAPI TestClient with mocked stores and API key authentication."""
    from fastapi.testclient import TestClient

    from kb.api.app import app, reset_stores, set_stores

    # Set test API key for authentication
    test_api_key = "test-api-key-12345"
    monkeypatch.setenv("DOLPHIN_API_KEY", test_api_key)

    sql_store, lance_store = mock_kb_stores
    set_stores(sql_store, lance_store)

    # Create client with default API key header for all requests
    client = TestClient(app)
    client.headers = {"X-API-Key": test_api_key}

    yield client

    reset_stores()


@pytest.fixture
def mock_pipeline():
    """Mock KB pipeline for testing indexing without real embedding calls."""
    from unittest.mock import AsyncMock

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

    return repo_dir


@pytest.fixture
def port() -> int:
    """Find a free port for testing."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        return s.getsockname()[1]
