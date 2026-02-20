from __future__ import annotations

from pathlib import Path

from kb.migrations import LATEST_SCHEMA_VERSION
from kb.store.sqlite_meta import SQLiteMetadataStore


def _insert_code_node(store: SQLiteMetadataStore, *, node_id: str, repo_id: int, file_id: int) -> None:
    with store._connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO code_nodes (
                id, node_type, name, qualified_name, repo_id, file_id, start_line, end_line,
                language, signature, docstring, visibility, is_async, is_generator,
                commit_sha, branch, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                node_id,
                "function",
                "legacy_fn",
                "legacy.module.legacy_fn",
                repo_id,
                file_id,
                1,
                10,
                "python",
                None,
                None,
                None,
                0,
                0,
                "abc123",
                "main",
            ),
        )
        conn.commit()


def test_initialize_migrates_legacy_code_node_aliases(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    store = SQLiteMetadataStore(db_path)
    store.initialize()

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store.record_repo("repo", repo_path)
    repo = store.get_repo_by_name("repo")
    assert repo is not None
    repo_id = int(repo["id"])

    file_id = store.upsert_file(
        repo_id=repo_id,
        path="legacy.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=10,
    )
    node_id = "legacy-node-id"
    _insert_code_node(store, node_id=node_id, repo_id=repo_id, file_id=file_id)

    with store._connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS code_node_aliases (
                id INTEGER PRIMARY KEY,
                node_id TEXT NOT NULL REFERENCES code_nodes(id),
                file_id INTEGER NOT NULL REFERENCES files(id),
                alias_name TEXT,
                alias_qualified_name TEXT,
                line_number INTEGER
            )
            """
        )
        cur.execute(
            """
            INSERT INTO code_node_aliases (
                id, node_id, file_id, alias_name, alias_qualified_name, line_number
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, node_id, file_id, "legacy_alias", "legacy.module.legacy_alias", 5),
        )
        cur.execute("UPDATE schema_version SET version = 0, updated_at = datetime('now') WHERE id = 1")
        conn.commit()

    restarted_store = SQLiteMetadataStore(db_path)
    restarted_store.initialize()

    with restarted_store._connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='code_node_aliases'")
        assert cur.fetchone() is None

        cur.execute(
            """
            SELECT alias_name, alias_qualified_name, line_number
            FROM node_aliases
            WHERE node_id = ? AND file_id = ?
            """,
            (node_id, file_id),
        )
        row = cur.fetchone()
        assert row is not None
        assert str(row[0]) == "legacy_alias"
        assert str(row[1]) == "legacy.module.legacy_alias"
        assert int(row[2]) == 5

        cur.execute("SELECT version FROM schema_version WHERE id = 1")
        version_row = cur.fetchone()
        assert version_row is not None
        assert int(version_row[0]) == LATEST_SCHEMA_VERSION


def test_initialize_rebuilds_file_snapshots_with_cascade(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    store = SQLiteMetadataStore(db_path)
    store.initialize()

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    store.record_repo("repo", repo_path)
    repo = store.get_repo_by_name("repo")
    assert repo is not None
    repo_id = int(repo["id"])

    file_id = store.upsert_file(
        repo_id=repo_id,
        path="snapshot.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=20,
    )

    with store._connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO file_snapshots (
                file_id, repo_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (file_id, repo_id, "snapshot.py", 1, 20, "hash"),
        )

        # Recreate legacy table without ON DELETE CASCADE.
        cur.execute("ALTER TABLE file_snapshots RENAME TO file_snapshots__legacy_no_cascade")
        cur.execute(
            """
            CREATE TABLE file_snapshots (
                file_id INTEGER PRIMARY KEY NOT NULL REFERENCES files(id),
                repo_id INTEGER NOT NULL REFERENCES repos(id),
                path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                last_indexed_at TEXT NOT NULL,
                CONSTRAINT uq_file_snapshot_repo_path UNIQUE (repo_id, path)
            )
            """
        )
        cur.execute(
            """
            INSERT INTO file_snapshots (
                file_id, repo_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at
            )
            SELECT
                file_id, repo_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at
            FROM file_snapshots__legacy_no_cascade
            """
        )
        cur.execute("DROP TABLE file_snapshots__legacy_no_cascade")
        cur.execute("UPDATE schema_version SET version = 0, updated_at = datetime('now') WHERE id = 1")
        conn.commit()

    restarted_store = SQLiteMetadataStore(db_path)
    restarted_store.initialize()

    with restarted_store._connect() as conn:
        cur = conn.cursor()
        fk_rows = cur.execute("PRAGMA foreign_key_list(file_snapshots)").fetchall()
        on_delete_map = {(str(row[2]), str(row[3])): str(row[6]).upper() for row in fk_rows}
        assert on_delete_map[("files", "file_id")] == "CASCADE"
        assert on_delete_map[("repos", "repo_id")] == "CASCADE"

        cur.execute("SELECT COUNT(*) FROM file_snapshots WHERE file_id = ?", (file_id,))
        row = cur.fetchone()
        assert row is not None
        assert int(row[0]) == 1
