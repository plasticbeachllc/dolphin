"""
Unit tests for SQLiteMetadataStore - Core operations

Tests basic database operations using the correct API
"""

import pytest

from kb.migrations import LATEST_SCHEMA_VERSION
from kb.store.connection_pool import close_connection_pool, get_connection_pool
from kb.store.sqlite_meta import SQLiteMetadataStore


@pytest.fixture
def meta_store(tmp_path):
    """Create a temporary SQLite metadata store."""
    db_path = tmp_path / "test.db"
    store = SQLiteMetadataStore(db_path)
    store.initialize()
    return store


def test_store_initialization(meta_store):
    """Test that store initializes successfully."""
    assert meta_store is not None
    summary = meta_store.summarize()
    assert "repos" in summary


def test_record_and_get_repo(meta_store, tmp_path):
    """Test recording and retrieving a repository."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()

    # Record repo
    meta_store.record_repo("test-repo", repo_path)

    # Get repo
    repo = meta_store.get_repo_by_name("test-repo")

    assert repo is not None
    assert "id" in repo
    assert repo["root_path"] == str(repo_path.resolve())


def test_list_all_repos(meta_store, tmp_path):
    """Test listing all repositories."""
    # Record multiple repos
    for i in range(3):
        repo_path = tmp_path / f"repo{i}"
        repo_path.mkdir()
        meta_store.record_repo(f"repo{i}", repo_path)

    repos = meta_store.list_all_repos()

    assert len(repos) == 3
    assert all("id" in r and "root_path" in r for r in repos)


def test_upsert_file(meta_store, tmp_path):
    """Test upserting a file."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)

    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]

    file_id = meta_store.upsert_file(
        repo_id=repo_id, path="src/test.py", ext=".py", language="python", is_binary=False, size_bytes=1024
    )

    assert file_id > 0


def test_upsert_file_returns_existing_id_on_conflict(tmp_path):
    """Ensure upsert_file returns the correct id when the row already exists."""
    db_path = tmp_path / "test.db"
    get_connection_pool(db_path, pool_size=1, max_overflow=0)
    store = SQLiteMetadataStore(db_path)
    store.initialize()

    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    store.record_repo("test-repo", repo_path)
    repo = store.get_repo_by_name("test-repo")
    assert repo is not None
    repo_id = repo["id"]

    file_a_id = store.upsert_file(
        repo_id=repo_id, path="src/a.py", ext=".py", language="python", is_binary=False, size_bytes=10
    )
    store.upsert_file(repo_id=repo_id, path="src/b.py", ext=".py", language="python", is_binary=False, size_bytes=20)
    file_a_id_again = store.upsert_file(
        repo_id=repo_id, path="src/a.py", ext=".py", language="python", is_binary=False, size_bytes=30
    )

    assert file_a_id_again == file_a_id
    close_connection_pool(db_path)


def test_get_file_by_path(meta_store, tmp_path):
    """Test retrieving a file by path."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)

    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]

    file_id = meta_store.upsert_file(
        repo_id=repo_id, path="src/test.py", ext=".py", language="python", is_binary=False, size_bytes=1024
    )

    file = meta_store.get_file_by_path(repo_id, "src/test.py")

    assert file is not None
    assert file["id"] == file_id
    assert file["path"] == "src/test.py"


def test_summarize(meta_store, tmp_path):
    """Test database summary."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)

    summary = meta_store.summarize()

    assert "repos" in summary
    assert "files" in summary
    assert "chunks" in summary
    assert summary["repos"] >= 1


def test_get_chunk_locations_by_identity(meta_store, tmp_path):
    """Test retrieving chunk locations by identity keys."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]

    file_id = meta_store.upsert_file(
        repo_id=repo_id, path="test.py", ext=".py", language="python", is_binary=False, size_bytes=100
    )

    # Insert test chunk content directly to setup state
    text_hash = "hash123"
    embed_model = "small"
    with meta_store._connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chunk_content (
                repo_id, file_id, text_hash, embed_model, id, first_indexed_at, last_indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_id, file_id, text_hash, embed_model, "uuid-123", "2024-01-01", "2024-01-01"),
        )
        content_id = "uuid-123"
        cur.execute(
            """
            INSERT INTO chunk_locations (
                content_id, start_line, end_line, symbol_name, symbol_path, symbol_kind, id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (content_id, 1, 10, "test_func", "test.test_func", "function", "loc-123"),
        )
        conn.commit()

    locations = meta_store.get_chunk_locations_by_identity(repo_id, file_id, text_hash, embed_model)

    assert len(locations) == 1
    assert locations[0]["content_id"] == str(content_id)
    assert locations[0]["start_line"] == 1
    assert locations[0]["end_line"] == 10
    assert locations[0]["symbol_name"] == "test_func"


def test_get_chunk_locations_fallback(meta_store, tmp_path):
    """Test that retrieving chunk locations falls back to available models if requested model is missing."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]

    file_id = meta_store.upsert_file(
        repo_id=repo_id, path="test.py", ext=".py", language="python", is_binary=False, size_bytes=100
    )

    # Insert test chunk content for "large" model ONLY
    text_hash = "hash123"
    existing_model = "large"
    requested_model = "small"

    with meta_store._connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chunk_content (
                repo_id, file_id, text_hash, embed_model, id, first_indexed_at, last_indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_id, file_id, text_hash, existing_model, "uuid-large", "2024-01-01", "2024-01-01"),
        )
        content_id = "uuid-large"
        cur.execute(
            """
            INSERT INTO chunk_locations (
                content_id, start_line, end_line, symbol_name, symbol_path, symbol_kind, id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (content_id, 1, 10, "test_func", "test.test_func", "function", "loc-1"),
        )
        conn.commit()

    # Request "small" model (which doesn't exist)
    # With fix, it should return locations from "large" model
    locations = meta_store.get_chunk_locations_by_identity(repo_id, file_id, text_hash, requested_model)

    assert len(locations) == 1
    assert locations[0]["content_id"] == "uuid-large"
    assert locations[0]["start_line"] == 1


def test_initialize_creates_schema_version_table(tmp_path):
    """Initialization should create schema_version tracking metadata."""
    db_path = tmp_path / "test.db"
    store = SQLiteMetadataStore(db_path)
    store.initialize()

    with store._connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_version WHERE id = 1")
        row = cur.fetchone()

    assert row is not None
    assert int(row[0]) == LATEST_SCHEMA_VERSION


def test_initialize_auto_applies_pending_schema_migrations(tmp_path, caplog):
    """Startup should auto-apply pending migrations and emit a user-facing note."""
    db_path = tmp_path / "test.db"
    store = SQLiteMetadataStore(db_path)
    store.initialize()

    # Simulate an older schema version before next startup.
    with store._connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE schema_version SET version = 0, updated_at = datetime('now') WHERE id = 1")
        conn.commit()

    restarted_store = SQLiteMetadataStore(db_path)
    with caplog.at_level("WARNING"):
        restarted_store.initialize()

    with restarted_store._connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_version WHERE id = 1")
        row = cur.fetchone()

    assert row is not None
    assert int(row[0]) == LATEST_SCHEMA_VERSION
    assert any("Auto-applied startup migration(s) to canonical schema" in rec.message for rec in caplog.records)
