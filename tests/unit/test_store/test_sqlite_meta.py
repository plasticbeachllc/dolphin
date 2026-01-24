"""Unit tests for SQLite metadata store operations."""

import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest

from kb.store.connection_pool import close_connection_pool
from kb.store.sqlite_meta import SQLiteMetadataStore


class TestSQLiteMetadataStore:
    """Test SQLite metadata store CRUD operations and session management."""

    def test_repo_operations(self, temp_db_path):
        """Test repository creation, retrieval, and duplicate handling."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        # Test record_repo and get_repo_by_name
        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path, default_embed_model="small")
        repo = store.get_repo_by_name("test-repo")

        assert repo is not None, "Repo should be found after record_repo"
        assert isinstance(repo["id"], int) and repo["id"] > 0
        assert repo["root_path"] == str(repo_path)
        assert repo["default_embed_model"] == "small"

        # Test duplicate repo handling - record_repo doesn't return ID, so we get it again
        store.record_repo("test-repo", repo_path)
        same_repo = store.get_repo_by_name("test-repo")
        assert same_repo is not None
        assert same_repo["id"] == repo["id"], "Duplicate repo should return same ID"

    def test_connection_pool_integration(self, temp_db_path):
        """Ensure metadata store reuses pooled connections for repeated queries."""

        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("pooled-repo", repo_path)
        store.get_repo_by_name("pooled-repo")
        store.get_repo_by_name("pooled-repo")

        pool = store._get_connection_pool()
        stats = pool.stats()

        assert stats["created_connections"] >= pool.pool_size
        assert stats["reused_connections"] >= 2

        close_connection_pool(temp_db_path)

    def test_session_management(self, temp_db_path):
        """Test session lifecycle and status transitions."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        # Test session creation
        session_id = store.begin_session(repo_id, "a" * 40, "main", "small")
        assert isinstance(session_id, int) and session_id > 0

        # Test counter updates - provide all required counters to avoid NULL constraints
        # Note: The bump_session_counters method only updates provided counters, doesn't set others to NULL
        store.bump_session_counters(session_id, files_indexed=5, chunks_indexed=2)

        # Verify counter updates
        def _query_one(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> tuple | None:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            con.close()
            return row

        row = _query_one(
            temp_db_path,
            "SELECT files_indexed, chunks_indexed, vectors_written FROM sessions WHERE id = ?",
            (session_id,),
        )
        assert row is not None
        assert row[0] == 5
        assert row[1] == 2
        assert row[2] == 0

        # Test session status transitions
        store.set_session_status(session_id, "succeeded", notes="done")
        row = _query_one(
            temp_db_path,
            "SELECT status, notes, ended_at FROM sessions WHERE id = ?",
            (session_id,),
        )
        assert row is not None
        assert row[0] == "succeeded"
        assert "done" in (row[1] or "")
        assert row[2] is not None, "ended_at should be set for terminal status"

        # Test invalid repo session creation
        with pytest.raises((sqlite3.IntegrityError, Exception)):
            store.begin_session(999999, "b" * 40, "main", "small")

    def test_file_operations(self, temp_db_path):
        """Test file upsert operations and commit tracking."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        # Test file upsert idempotency
        file_id = store.upsert_file(
            repo_id,
            path="src/a.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=123,
        )
        assert isinstance(file_id, int) and file_id > 0

        # Second upsert returns same id and does not create duplicates
        file_id2 = store.upsert_file(
            repo_id,
            path="src/a.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=456,
        )
        assert file_id == file_id2

        # Verify only one record exists and size was updated
        row = _query_one(
            temp_db_path,
            "SELECT COUNT(1), size_bytes FROM files WHERE repo_id = ? AND path = ?",
            (repo_id, "src/a.py"),
        )
        assert row is not None
        assert row[0] == 1
        assert row[1] == 456

        # Test commit tracking
        store.set_file_latest_commit(repo_id, "src/a.py", "c" * 40)
        row = _query_one(
            temp_db_path,
            "SELECT latest_commit_sha FROM files WHERE repo_id = ? AND path = ?",
            (repo_id, "src/a.py"),
        )
        assert row is not None
        assert row[0] == "c" * 40

    def test_chunk_content_operations(self, temp_db_path):
        """Test chunk content storage and hash-based deduplication."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        file_id = store.upsert_file(
            repo_id,
            path="src/a.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=123,
        )

        # Test chunk content hashing APIs start empty
        assert store.get_existing_content_hashes_for_file(repo_id, file_id, "small") == set()

        # Test content upsert
        hash_a = "a" * 64
        cid_a1 = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")
        assert isinstance(cid_a1, str) and len(cid_a1) > 0

        # Re-upsert should return same id and just bump last_indexed_at
        cid_a2 = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")
        assert cid_a1 == cid_a2
        assert store.get_existing_content_hashes_for_file(repo_id, file_id, "small") == {hash_a}

    def test_location_synchronization(self, temp_db_path):
        """Test chunk location tracking and synchronization."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        file_id = store.upsert_file(
            repo_id,
            path="src/a.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=123,
        )

        hash_a = "a" * 64
        cid_a = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")

        # Test location sync insert/update/delete operations
        first_locations = [
            {
                "start_line": 1,
                "end_line": 5,
                "symbol_kind": "class",
                "symbol_name": "Widget",
                "symbol_path": "Widget",
            },
            {
                "start_line": 8,
                "end_line": 12,
                "symbol_kind": "method",
                "symbol_name": "Widget.render",
                "symbol_path": "Widget.render",
            },
        ]
        stats = store.sync_locations_for_content_row(cid_a, first_locations)
        assert stats == {"inserted": 2, "updated": 0, "deleted": 0}

        locations_after_first = store.get_existing_locations_for_content_ids([cid_a])
        assert cid_a in locations_after_first
        assert len(locations_after_first[cid_a]) == 2

        # Test location updates and deletions
        second_locations = [
            {
                "start_line": 1,
                "end_line": 5,
                "symbol_kind": "class",
                "symbol_name": "WidgetRenamed",
                "symbol_path": "WidgetRenamed",
            },
            {
                "start_line": 20,
                "end_line": 24,
                "symbol_kind": "method",
                "symbol_name": "Widget.debug",
                "symbol_path": "Widget.debug",
            },
        ]
        stats = store.sync_locations_for_content_row(cid_a, second_locations)
        assert stats == {"inserted": 1, "updated": 1, "deleted": 1}

        locations_after_second = store.get_existing_locations_for_content_ids([cid_a])
        assert len(locations_after_second[cid_a]) == 2
        names = {loc["symbol_name"] for loc in locations_after_second[cid_a]}
        assert names == {"WidgetRenamed", "Widget.debug"}

    def test_rm_repo_cleans_graph_and_sync_tables(self, temp_db_path):
        """Ensure rm_repo_enhanced deletes graph and file sync tables before repo removal."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        file_id = store.upsert_file(
            repo_id,
            path="src/a.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=123,
        )

        now = "2024-01-01T00:00:00Z"
        node_id_a = str(uuid.uuid4())
        node_id_b = str(uuid.uuid4())
        edge_id = str(uuid.uuid4())
        alias_id = str(uuid.uuid4())
        xref_id = str(uuid.uuid4())

        with sqlite3.connect(temp_db_path) as conn:
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO pending_changes
                (repo_id, file_path, change_type, detected_at, processed, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (repo_id, "src/a.py", "modified", now, 0, None),
            )

            cur.execute(
                """
                INSERT INTO file_snapshots
                (file_id, repo_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (file_id, repo_id, "src/a.py", 123456789, 123, "a" * 64, now),
            )

            cur.execute(
                """
                INSERT INTO code_nodes
                (id, node_type, name, qualified_name, repo_id, file_id, start_line, end_line, language,
                 signature, docstring, visibility, is_async, is_generator,
                 commit_sha, branch, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    node_id_a,
                    "function",
                    "alpha",
                    "pkg.alpha",
                    repo_id,
                    file_id,
                    1,
                    5,
                    "python",
                    "alpha()",
                    "doc",
                    "public",
                    0,
                    0,
                    "a" * 40,
                    "main",
                    now,
                    now,
                ),
            )

            cur.execute(
                """
                INSERT INTO code_nodes
                (id, node_type, name, qualified_name, repo_id, file_id, start_line, end_line, language,
                 signature, docstring, visibility, is_async, is_generator,
                 commit_sha, branch, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    node_id_b,
                    "function",
                    "beta",
                    "pkg.beta",
                    repo_id,
                    file_id,
                    10,
                    12,
                    "python",
                    "beta()",
                    "doc",
                    "public",
                    0,
                    0,
                    "b" * 40,
                    "main",
                    now,
                    now,
                ),
            )

            cur.execute(
                """
                INSERT INTO code_edges
                (id, source_node_id, target_node_id, edge_type, repo_id, line_number, is_direct,
                 relationship_metadata, commit_sha, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    edge_id,
                    node_id_a,
                    node_id_b,
                    "calls",
                    repo_id,
                    2,
                    1,
                    None,
                    "a" * 40,
                    now,
                    now,
                ),
            )

            cur.execute(
                """
                INSERT INTO node_aliases
                (id, node_id, file_id, alias_name, alias_qualified_name, line_number)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (alias_id, node_id_a, file_id, "alpha_alias", "pkg.alpha_alias", 3),
            )

            cur.execute(
                """
                INSERT INTO graph_metrics
                (node_id, pagerank, betweenness_centrality, in_degree, out_degree, cyclomatic_complexity,
                 community_id, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (node_id_a, 0.1, 0.0, 1, 1, 1, 1, now),
            )

            cur.execute(
                """
                INSERT INTO cross_repo_references
                (id, source_node_id, source_repo_id, target_package, target_module, target_symbol,
                 reference_type, file_id, line_number, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    xref_id,
                    node_id_a,
                    repo_id,
                    "requests",
                    "requests",
                    "get",
                    "import",
                    file_id,
                    4,
                    now,
                    now,
                ),
            )

            cur.execute(
                """
                INSERT INTO code_nodes_fts
                (node_id, qualified_name, name, signature, docstring)
                VALUES (?, ?, ?, ?, ?)
            """,
                (node_id_a, "pkg.alpha", "alpha", "alpha()", "doc"),
            )

            cur.execute(
                """
                INSERT INTO graph_snapshots
                (repo_id, commit_sha, commit_message, commit_timestamp, node_count, edge_count, snapshot_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (repo_id, "a" * 40, "msg", now, 2, 1, None, now),
            )

            cur.execute(
                """
                INSERT INTO graph_cache_state
                (repo_id, commit_sha, last_rebuild_at, node_count, edge_count, edge_changes_since_rebuild)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (repo_id, "a" * 40, now, 2, 1, 0),
            )

            conn.commit()

        store.rm_repo_enhanced("test-repo")

        def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
            con = sqlite3.connect(temp_db_path)
            cur = con.cursor()
            cur.execute(sql, params)
            value = int(cur.fetchone()[0])
            con.close()
            return value

        assert store.get_repo_by_name("test-repo") is None
        assert _count("SELECT COUNT(*) FROM file_snapshots WHERE repo_id = ?", (repo_id,)) == 0
        assert _count("SELECT COUNT(*) FROM pending_changes WHERE repo_id = ?", (repo_id,)) == 0
        assert _count("SELECT COUNT(*) FROM code_nodes WHERE repo_id = ?", (repo_id,)) == 0
        assert _count("SELECT COUNT(*) FROM code_edges WHERE repo_id = ?", (repo_id,)) == 0
        assert (
            _count(
                "SELECT COUNT(*) FROM node_aliases WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)",
                (repo_id,),
            )
            == 0
        )
        assert (
            _count(
                "SELECT COUNT(*) FROM code_nodes_fts WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)",
                (repo_id,),
            )
            == 0
        )
        assert (
            _count(
                "SELECT COUNT(*) FROM graph_metrics WHERE node_id IN (SELECT id FROM code_nodes WHERE repo_id = ?)",
                (repo_id,),
            )
            == 0
        )
        assert _count("SELECT COUNT(*) FROM cross_repo_references WHERE source_repo_id = ?", (repo_id,)) == 0
        assert _count("SELECT COUNT(*) FROM graph_snapshots WHERE repo_id = ?", (repo_id,)) == 0
        assert _count("SELECT COUNT(*) FROM graph_cache_state WHERE repo_id = ?", (repo_id,)) == 0

    def test_pruning_operations(self, temp_db_path):
        """Test pruning of invalidated content."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        file_id = store.upsert_file(
            repo_id,
            path="src/a.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=123,
        )

        # Create multiple content entries
        hash_a = "a" * 64
        hash_b = "b" * 64
        cid_a = store.upsert_chunk_content_row(repo_id, file_id, hash_a, "small")
        cid_b = store.upsert_chunk_content_row(repo_id, file_id, hash_b, "small")
        assert cid_b != cid_a

        # Prune should remove content not in current hashes
        pruned = store.prune_invalidated_content_for_file(repo_id, file_id, "small", {hash_a})
        assert pruned == 1
        hashes_after_prune = store.get_existing_content_hashes_for_file(repo_id, file_id, "small")
        assert hashes_after_prune == {hash_a}

    def test_sync_file_state_end_to_end(self, temp_db_path):
        """Test complete file state synchronization."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None
        repo_id = int(repo["id"])

        file_id = store.upsert_file(
            repo_id,
            path="src/a.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=123,
        )

        # Test sync_file_state with multiple content entries
        desired = {
            "a" * 64: [
                {
                    "start_line": 1,
                    "end_line": 5,
                    "symbol_kind": "class",
                    "symbol_name": "WidgetRenamed",
                    "symbol_path": "WidgetRenamed",
                }
            ],
            "c" * 64: [
                {
                    "start_line": 30,
                    "end_line": 40,
                    "symbol_kind": None,
                    "symbol_name": None,
                    "symbol_path": None,
                }
            ],
        }
        stats = store.sync_file_state(repo_id, file_id, "small", desired)
        assert stats["content_upserted"] == len(desired)
        assert stats["locations_inserted"] >= 1

        hashes_final = store.get_existing_content_hashes_for_file(repo_id, file_id, "small")
        assert hashes_final == set(desired.keys())

    def test_summarize_operations(self, temp_db_path):
        """Test store summarization functionality."""
        store = SQLiteMetadataStore(temp_db_path)
        store.initialize()

        repo_path = Path("/mock/repo")
        store.record_repo("test-repo", repo_path)

        summary = store.summarize()
        assert summary["repos"] >= 1
        assert summary["files"] >= 0  # Could be 0 if no files added


# Helper function for direct database queries
def _query_one(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> tuple | None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    con.close()
    return row
