from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from pb_kb.store.sqlite_meta import SQLiteMetadataStore


def _query_one(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> tuple | None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    con.close()
    return row


def run_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_knowledge.db"
        store = SQLiteMetadataStore(db_path)
        store.initialize()

        # Test record_repo and get_repo_by_name
        repo_path = Path(td) / "repo_root"
        repo_path.mkdir()
        store.record_repo("test-repo", repo_path, default_embed_model="small")
        repo = store.get_repo_by_name("test-repo")
        assert repo is not None, "Repo should be found after record_repo"
        assert isinstance(repo["id"], int) and repo["id"] > 0
        assert repo["root_path"] == str(repo_path)
        assert repo["default_embed_model"] == "small"

        repo_id = int(repo["id"])

        # begin_session requires a valid repo_id
        session_id = store.begin_session(repo_id, "" + "a" * 40, "main", "small")
        assert isinstance(session_id, int) and session_id > 0

        # bump counters
        store.bump_session_counters(session_id, files_indexed=5, chunks_indexed=2)
        row = _query_one(db_path, "SELECT files_indexed, chunks_indexed, vectors_written FROM sessions WHERE id = ?", (session_id,))
        assert row is not None
        assert row[0] == 5
        assert row[1] == 2
        assert row[2] == 0

        # set session status to succeeded
        store.set_session_status(session_id, "succeeded", notes="done")
        row = _query_one(db_path, "SELECT status, notes, ended_at FROM sessions WHERE id = ?", (session_id,))
        assert row is not None
        assert row[0] == "succeeded"
        assert "done" in (row[1] or "")
        assert row[2] is not None, "ended_at should be set for terminal status"

        # begin_session with invalid repo should raise IntegrityError
        raised = False
        try:
            store.begin_session(999999, "" + "b" * 40, "main", "small")
        except sqlite3.IntegrityError:
            raised = True
        except Exception:
            # Other DB errors may also indicate failure; treat as raised
            raised = True
        assert raised, "begin_session with invalid repo_id should raise"

        # upsert_file idempotency
        file_id = store.upsert_file(repo_id, path="src/a.py", ext=".py", language="python", is_binary=False, size_bytes=123)
        assert isinstance(file_id, int) and file_id > 0
        # second upsert returns same id and does not create duplicates
        file_id2 = store.upsert_file(repo_id, path="src/a.py", ext=".py", language="python", is_binary=False, size_bytes=456)
        assert file_id == file_id2
        row = _query_one(db_path, "SELECT COUNT(1), size_bytes FROM files WHERE repo_id = ? AND path = ?", (repo_id, "src/a.py"))
        assert row is not None
        assert row[0] == 1
        # size_bytes should have been updated to the last value
        assert row[1] == 456

        # set_file_latest_commit
        store.set_file_latest_commit(repo_id, "src/a.py", "" + "c" * 40)
        row = _query_one(db_path, "SELECT latest_commit_sha FROM files WHERE repo_id = ? AND path = ?", (repo_id, "src/a.py"))
        assert row is not None
        assert row[0] == "" + "c" * 40

        # summarise should reflect repos and files
        summary = store.summarize()
        assert summary["repos"] >= 1
        assert summary["files"] >= 1

    print("SQLiteMetadataStore tests passed")
