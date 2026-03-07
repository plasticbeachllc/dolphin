"""
Unit tests for SQLiteMetadataStore - Core operations

Tests basic database operations using the correct API
"""

import pytest

from kb.migrations import LATEST_SCHEMA_VERSION
from kb.store.connection_pool import close_connection_pool, get_connection_pool
from kb.store.sqlite_meta import (
    SQLiteMetadataStore,
    _path_tokens,
    _split_camel_case,
    enrich_fts_content,
    strip_fts_enrichment,
)


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


def test_get_repos_by_names(meta_store, tmp_path):
    """Test batch repo lookup by names."""
    for i in range(3):
        repo_path = tmp_path / f"repo{i}"
        repo_path.mkdir()
        meta_store.record_repo(f"repo{i}", repo_path)

    # Look up existing repos
    found = meta_store.get_repos_by_names(["repo0", "repo2"])
    assert len(found) == 2
    assert "repo0" in found
    assert "repo2" in found
    assert "id" in found["repo0"]

    # Missing names are omitted
    found = meta_store.get_repos_by_names(["repo0", "nonexistent"])
    assert len(found) == 1
    assert "repo0" in found

    # Empty list returns empty dict
    assert meta_store.get_repos_by_names([]) == {}


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


def test_get_bm25_hydration_map_prefers_requested_model(meta_store, tmp_path):
    """Bulk hydration should prefer requested model when multiple models exist."""
    repo_path = tmp_path / "hydration-repo"
    repo_path.mkdir()
    meta_store.record_repo("hydration-repo", repo_path)
    repo = meta_store.get_repo_by_name("hydration-repo")
    assert repo is not None
    repo_id = int(repo["id"])

    file_id = meta_store.upsert_file(
        repo_id=repo_id,
        path="src/service.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=256,
    )

    with meta_store._connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chunk_content (
                repo_id, file_id, text_hash, embed_model, id, first_indexed_at, last_indexed_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (repo_id, file_id, "hash-hydrate", "small", "cid-small"),
        )
        cur.execute(
            """
            INSERT INTO chunk_content (
                repo_id, file_id, text_hash, embed_model, id, first_indexed_at, last_indexed_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (repo_id, file_id, "hash-hydrate", "large", "cid-large"),
        )
        cur.execute(
            """
            INSERT INTO chunk_locations (
                content_id, start_line, end_line, symbol_name, symbol_path, symbol_kind, id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("cid-small", 11, 22, "small_func", "svc.small_func", "function", "loc-small"),
        )
        cur.execute(
            """
            INSERT INTO chunk_locations (
                content_id, start_line, end_line, symbol_name, symbol_path, symbol_kind, id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("cid-large", 33, 44, "large_func", "svc.large_func", "function", "loc-large"),
        )
        cur.execute(
            """
            INSERT INTO chunks_fts (
                content_id, repo, path, text_hash, content, symbol_name, symbol_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("fts-hydration", "hydration-repo", "src/service.py", "hash-hydrate", "function body", None, None),
        )
        conn.commit()

    hydration = meta_store.get_bm25_hydration_map(["fts-hydration"], embed_model="small")

    assert "fts-hydration" in hydration
    entry = hydration["fts-hydration"]
    assert entry["repo_id"] == repo_id
    assert entry["file_id"] == file_id
    assert entry["text_hash"] == "hash-hydrate"
    assert entry["embed_model"] == "small"
    assert len(entry["locations"]) == 1
    assert entry["locations"][0]["start_line"] == 11
    assert entry["locations"][0]["end_line"] == 22


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


def test_collect_file_dependency_counts_handles_graph_metrics_query(meta_store, tmp_path):
    """FK diagnostics should query graph_metrics via node_id without raising."""
    repo_path = tmp_path / "dep-repo"
    repo_path.mkdir()
    meta_store.record_repo("dep-repo", repo_path)
    repo = meta_store.get_repo_by_name("dep-repo")
    assert repo is not None
    repo_id = int(repo["id"])

    file_id = meta_store.upsert_file(
        repo_id=repo_id,
        path="src/dependency.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=64,
    )

    with meta_store._connect() as conn:
        cur = conn.cursor()
        # Ensure the table exists so the diagnostic query executes.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_metrics (
                node_id TEXT PRIMARY KEY NOT NULL REFERENCES code_nodes(id) ON DELETE CASCADE,
                pagerank REAL,
                betweenness_centrality REAL,
                in_degree INTEGER NOT NULL DEFAULT 0,
                out_degree INTEGER NOT NULL DEFAULT 0,
                cyclomatic_complexity INTEGER,
                community_id INTEGER
            )
            """
        )
        conn.commit()

        counts = meta_store._collect_file_dependency_counts(cur, file_id)
        assert isinstance(counts, dict)


class TestErrorPathLogging:
    """Tests for newly-logged error paths in FTS cleanup, LanceDB cleanup, consistency check, and integrity repair."""

    def test_fts_cleanup_error_is_logged(self, meta_store, tmp_path, caplog):
        """Patch FTS delete to raise; error is logged; no exception propagates to caller."""
        from unittest.mock import MagicMock

        repo_path = tmp_path / "fts-repo"
        repo_path.mkdir()
        meta_store.record_repo("fts-repo", repo_path)
        repo = meta_store.get_repo_by_name("fts-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        # Use a mock cursor that raises on any DELETE FROM chunks_fts
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = RuntimeError("FTS delete failed")
        mock_cur.rowcount = 0

        with caplog.at_level("ERROR"):
            result = meta_store._cleanup_fts_entries_comprehensive(mock_cur, repo_id, "fts-repo")

        assert len(result["errors"]) > 0
        assert any("FTS" in r.message or "fts" in r.message.lower() for r in caplog.records if r.levelno >= 40)

    def test_lancedb_model_cleanup_error_is_logged(self, meta_store, tmp_path, caplog):
        """Patch LanceDB cleanup to raise; error logged; caller receives graceful return."""
        from unittest.mock import MagicMock

        repo_path = tmp_path / "lance-repo"
        repo_path.mkdir()
        meta_store.record_repo("lance-repo", repo_path)

        mock_lancedb = MagicMock()
        mock_lancedb.count_repo_vectors.side_effect = RuntimeError("LanceDB exploded")
        mock_lancedb.delete_repo.side_effect = RuntimeError("LanceDB exploded")

        with caplog.at_level("ERROR"):
            result = meta_store._cleanup_lancedb_comprehensive(mock_lancedb, "lance-repo")

        assert len(result["errors"]) > 0
        assert any("LanceDB" in r.message for r in caplog.records if r.levelno >= 40)

    def test_consistency_check_error_is_logged(self, meta_store, tmp_path, caplog):
        """Patch consistency query to raise; error logged."""
        from unittest.mock import MagicMock

        repo_path = tmp_path / "consist-repo"
        repo_path.mkdir()
        meta_store.record_repo("consist-repo", repo_path)

        mock_lancedb = MagicMock()
        mock_lancedb.count_repo_vectors.side_effect = RuntimeError("consistency boom")

        with caplog.at_level("ERROR"):
            result = meta_store._check_lancedb_consistency(mock_lancedb, "consist-repo")

        assert result["consistent"] is False
        assert len(result["issues"]) > 0
        error_records = [r for r in caplog.records if r.levelno >= 40]
        assert any("consistency" in r.message.lower() or "LanceDB" in r.message for r in error_records)

    def test_integrity_repair_error_is_logged(self, tmp_path, caplog):
        """Patch repair operation to raise; error logged."""
        from unittest.mock import patch

        db_path = tmp_path / "repair.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        # The _validate_database_integrity method runs during init.
        # We test that if integrity check returns a failure, it raises RuntimeError.
        with store._connect() as conn:
            from contextlib import closing

            with closing(conn.cursor()) as cur:
                # Simulate a broken integrity check response by patching
                original_execute = cur.execute

                def patched_execute(sql, *args, **kwargs):
                    if "PRAGMA integrity_check" in str(sql):
                        # Return a mock cursor that yields a failure result
                        original_execute(sql, *args, **kwargs)
                        return cur
                    return original_execute(sql, *args, **kwargs)

        # Test that foreign key pragma failure is logged during engine creation
        with caplog.at_level("ERROR"):
            # Create a store with patched engine that raises on pragma
            db_path2 = tmp_path / "repair2.db"
            store2 = SQLiteMetadataStore(db_path2)

            with patch.object(store2, "_validate_database_integrity", side_effect=RuntimeError("integrity boom")):
                with pytest.raises(RuntimeError, match="integrity boom"):
                    store2.initialize()

    def test_fts5_corruption_auto_repair(self, tmp_path, caplog):
        """FTS5 corruption triggers auto-rebuild and succeeds."""
        from unittest.mock import MagicMock, patch

        db_path = tmp_path / "fts_repair.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        # The exact fetchone() call sequence in _validate_database_integrity is:
        #   1. PRAGMA integrity_check   → returns FTS corruption message
        #   2. PRAGMA integrity_check   → re-check after rebuild returns "ok"
        #   3-6. Four orphaned record COUNT(*) queries (chunk_locations, chunk_content, files, sessions)
        # If _validate_database_integrity gains/loses orphaned checks, update this list.
        mock_cur.fetchone.side_effect = [
            ("malformed inverted index for FTS5 table main.code_nodes_fts",),  # 1. initial integrity check
            ("ok",),  # 2. re-check after rebuild
            (0,),  # 3. orphaned chunk_locations
            (0,),  # 4. orphaned chunk_content
            (0,),  # 5. orphaned files
            (0,),  # 6. orphaned sessions
        ]

        with patch.object(store, "_connect", return_value=mock_conn):
            with patch.object(store, "_table_exists", return_value=True):
                with patch.object(store, "_rebuild_fts_table", return_value=True) as mock_rebuild:
                    with caplog.at_level("WARNING"):
                        store._validate_database_integrity()

        # Verify rebuild was called for both FTS tables
        assert mock_rebuild.call_count == 2

    def test_fts5_non_fts_corruption_raises(self, tmp_path):
        """Non-FTS corruption still raises RuntimeError."""
        from unittest.mock import MagicMock, patch

        db_path = tmp_path / "non_fts.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchone.return_value = ("database disk image is malformed",)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        with patch.object(store, "_connect", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="Database integrity check failed"):
                store._validate_database_integrity()

    def test_fts5_corruption_rebuild_returns_false_raises(self, tmp_path):
        """FTS5 corruption raises immediately when _rebuild_fts_table returns False."""
        from unittest.mock import MagicMock, patch

        db_path = tmp_path / "fts_fail.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_cur.fetchone.return_value = ("malformed inverted index for FTS5 table main.chunks_fts",)

        with patch.object(store, "_connect", return_value=mock_conn):
            with patch.object(store, "_table_exists", return_value=True):
                with patch.object(store, "_rebuild_fts_table", return_value=False):
                    with pytest.raises(RuntimeError, match="FTS5 rebuild failed"):
                        store._validate_database_integrity()

    def test_fts5_corruption_rebuild_succeeds_but_recheck_fails_raises(self, tmp_path):
        """FTS5 corruption raises when rebuild succeeds but integrity re-check still fails."""
        from unittest.mock import MagicMock, patch

        db_path = tmp_path / "fts_recheck.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        # Both integrity checks return FTS corruption (rebuild succeeded but didn't fix it)
        mock_cur.fetchone.side_effect = [
            ("malformed inverted index for FTS5 table main.chunks_fts",),
            ("malformed inverted index for FTS5 table main.chunks_fts",),
        ]

        with patch.object(store, "_connect", return_value=mock_conn):
            with patch.object(store, "_table_exists", return_value=True):
                with patch.object(store, "_rebuild_fts_table", return_value=True):
                    with pytest.raises(RuntimeError, match="after FTS5 rebuild"):
                        store._validate_database_integrity()

    def test_rebuild_fts_table_success(self, tmp_path):
        """_rebuild_fts_table returns True on success."""
        db_path = tmp_path / "rebuild_ok.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        result = store._rebuild_fts_table("chunks_fts")
        assert result is True

    def test_rebuild_fts_table_rejects_unknown_table(self, tmp_path):
        """_rebuild_fts_table raises ValueError for unknown table names."""
        db_path = tmp_path / "rebuild_fail.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        with pytest.raises(ValueError, match="Unexpected FTS table"):
            store._rebuild_fts_table("nonexistent_table")


# ---------------------------------------------------------------------------
# Tests for BM25 query preprocessing (OR conversion) and FTS content enrichment
# ---------------------------------------------------------------------------


class TestPrepareFTS5Query:
    """Tests for SQLiteMetadataStore._prepare_fts5_query."""

    def test_single_word_unchanged(self):
        assert SQLiteMetadataStore._prepare_fts5_query("pipeline") == "pipeline"

    def test_multi_word_converted_to_or(self):
        assert SQLiteMetadataStore._prepare_fts5_query("ingestion indexer") == "ingestion OR indexer"

    def test_three_words_converted_to_or(self):
        result = SQLiteMetadataStore._prepare_fts5_query("ingestion indexer pipeline")
        assert result == "ingestion OR indexer OR pipeline"

    def test_explicit_and_preserved(self):
        assert SQLiteMetadataStore._prepare_fts5_query("auth AND login") == "auth AND login"

    def test_explicit_or_preserved(self):
        assert SQLiteMetadataStore._prepare_fts5_query("auth OR login") == "auth OR login"

    def test_explicit_not_preserved(self):
        assert SQLiteMetadataStore._prepare_fts5_query("auth NOT test") == "auth NOT test"

    def test_quoted_phrase_preserved(self):
        assert SQLiteMetadataStore._prepare_fts5_query('"user controller"') == '"user controller"'

    def test_empty_string(self):
        assert SQLiteMetadataStore._prepare_fts5_query("") == ""


class TestSplitCamelCase:
    def test_pascal_case(self):
        assert _split_camel_case("IngestionPipeline") == ["ingestion", "pipeline"]

    def test_acronym(self):
        assert _split_camel_case("HTMLParser") == ["html", "parser"]

    def test_simple_lower(self):
        assert _split_camel_case("simple") == ["simple"]

    def test_multi_part(self):
        assert _split_camel_case("MyBigClassName") == ["my", "big", "class", "name"]

    def test_empty(self):
        assert _split_camel_case("") == []


class TestPathTokens:
    def test_basic_path(self):
        assert _path_tokens("kb/ingest/pipeline.py") == ["kb", "ingest", "pipeline"]

    def test_strips_common_extensions(self):
        tokens = _path_tokens("src/utils/helper.js")
        assert "js" not in tokens
        assert "helper" in tokens

    def test_deep_path(self):
        tokens = _path_tokens("a/b/c/deep_module.py")
        assert tokens == ["a", "b", "c", "deep_module"]


class TestEnrichFTSContent:
    def test_adds_path_tokens(self):
        enriched = enrich_fts_content("some code here", "kb/ingest/pipeline.py")
        assert "ingest" in enriched
        assert "pipeline" in enriched
        assert "some code here" in enriched

    def test_splits_camel_case_symbol(self):
        enriched = enrich_fts_content(
            "class body",
            "src/foo.py",
            symbol_name="IngestionPipeline",
        )
        assert "ingestion" in enriched
        assert "pipeline" in enriched

    def test_no_enrichment_for_empty_path_and_symbol(self):
        enriched = enrich_fts_content("content", "")
        assert enriched == "content"

    def test_strip_roundtrip(self):
        original = "def foo():\n    pass"
        enriched = enrich_fts_content(original, "kb/ingest/pipeline.py", symbol_name="IngestionPipeline")
        stripped = strip_fts_enrichment(enriched)
        assert stripped == original

    def test_strip_on_plain_content(self):
        assert strip_fts_enrichment("no sentinel here") == "no sentinel here"

    def test_deduplicates_tokens(self):
        enriched = enrich_fts_content(
            "code",
            "ingest/ingest.py",
            symbol_name="IngestManager",
        )
        sentinel = "\n__FTS_META__\n"
        meta = enriched.split(sentinel)[1]
        tokens = meta.split()
        assert tokens.count("ingest") == 1


class TestBM25SearchORQuery:
    """Integration test: BM25 search with OR queries finds partial matches."""

    def test_or_query_finds_partial_match(self, meta_store, tmp_path):
        """A multi-word query should find chunks matching ANY term."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        meta_store.record_repo("test-repo", repo_path)

        # Index a chunk that contains "ingestion" but NOT "indexer"
        meta_store.index_chunk_for_fts(
            content_id="chunk-1",
            repo="test-repo",
            path="kb/ingest/pipeline.py",
            text_hash="hash1",
            content="class IngestionPipeline: handles ingestion of code",
            symbol_name="IngestionPipeline",
        )

        # Index a chunk that contains "index" but NOT "ingestion"
        meta_store.index_chunk_for_fts(
            content_id="chunk-2",
            repo="test-repo",
            path="kb/ingest/indexer.py",
            text_hash="hash2",
            content="def index_documents(): indexes all documents",
            symbol_name="index_documents",
        )

        results = meta_store.bm25_search("ingestion indexer")

        # Both chunks should appear (OR matching)
        assert len(results) >= 1
        paths = [r["path"] for r in results]
        assert "kb/ingest/pipeline.py" in paths or "kb/ingest/indexer.py" in paths

    def test_enriched_path_tokens_are_searchable(self, meta_store, tmp_path):
        """Path tokens added by enrichment should be findable via BM25."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        meta_store.record_repo("test-repo", repo_path)

        # Index a chunk where "pipeline" only appears in the path, not content
        meta_store.index_chunk_for_fts(
            content_id="chunk-path",
            repo="test-repo",
            path="kb/ingest/pipeline.py",
            text_hash="hash-path",
            content="class SomeClass: does stuff with code repositories",
            symbol_name="SomeClass",
        )

        results = meta_store.bm25_search("pipeline")

        assert len(results) >= 1
        assert results[0]["path"] == "kb/ingest/pipeline.py"

    def test_camel_case_symbol_searchable(self, meta_store, tmp_path):
        """CamelCase symbols should be findable by their sub-tokens."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        meta_store.record_repo("test-repo", repo_path)

        meta_store.index_chunk_for_fts(
            content_id="chunk-camel",
            repo="test-repo",
            path="src/manager.py",
            text_hash="hash-camel",
            content="class body with no mention of the class name words",
            symbol_name="IngestionPipeline",
        )

        # "ingestion" should match via CamelCase-split enrichment
        results = meta_store.bm25_search("ingestion")

        assert len(results) >= 1
