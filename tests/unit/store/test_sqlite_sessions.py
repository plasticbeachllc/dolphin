"""
Additional tests for SQLiteMetadataStore - Session and file management

Tests session lifecycle, file operations, and database queries
"""

import pytest
from pathlib import Path
from kb.store.sqlite_meta import SQLiteMetadataStore


@pytest.fixture
def meta_store(tmp_path):
    """Create a temporary SQLite metadata store."""
    db_path = tmp_path / "test.db"
    store = SQLiteMetadataStore(db_path)
    store.initialize()
    return store


def test_begin_session(meta_store, tmp_path):
    """Test creating a new session."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]
    
    session_id = meta_store.begin_session(
        repo_id=repo_id,
        commit_sha="abc123",
        branch="main",
        embed_model="small"
    )
    
    assert session_id > 0


def test_get_session(meta_store, tmp_path):
    """Test retrieving a session."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]
    
    session_id = meta_store.begin_session(
        repo_id=repo_id,
        commit_sha="abc123",
        branch="main",
        embed_model="small"
    )
    
    session = meta_store.get_session(session_id)
    
    assert session is not None
    assert session["id"] == session_id
    assert session["commit_sha"] == "abc123"


def test_set_session_status(meta_store, tmp_path):
    """Test updating session status."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    session_id = meta_store.begin_session(
        repo_id=repo["id"],
        commit_sha="abc123",
        branch="main",
        embed_model="small"
    )
    
    meta_store.set_session_status(session_id, "succeeded")
    
    session = meta_store.get_session(session_id)
    assert session["status"] == "succeeded"


def test_bump_session_counters(meta_store, tmp_path):
    """Test updating session counters."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    session_id = meta_store.begin_session(
        repo_id=repo["id"],
        commit_sha="abc123",
        branch="main",
        embed_model="small"
    )
    
    meta_store.bump_session_counters(
        session_id,
        files_indexed=10,
        chunks_indexed=50
    )
    
    session = meta_store.get_session(session_id)
    assert session["files_indexed"] == 10
    assert session["chunks_indexed"] == 50


def test_get_file_id(meta_store, tmp_path):
    """Test getting file ID by path."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]
    
    file_id = meta_store.upsert_file(
        repo_id=repo_id,
        path="test.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=100
    )
    
    retrieved_id = meta_store.get_file_id(repo_id, "test.py")
    assert retrieved_id == file_id


def test_get_file_id_not_found(meta_store, tmp_path):
    """Test getting file ID for non-existent file."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    file_id = meta_store.get_file_id(repo["id"], "nonexistent.py")
    
    assert file_id is None


def test_set_file_latest_commit(meta_store, tmp_path):
    """Test updating file's latest commit."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]
    
    meta_store.upsert_file(
        repo_id=repo_id,
        path="test.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=100
    )
    
    meta_store.set_file_latest_commit(repo_id, "test.py", "new_commit_sha")
    
    file = meta_store.get_file_by_path(repo_id, "test.py")
    assert file["latest_commit_sha"] == "new_commit_sha"


def test_get_last_successful_commit(meta_store, tmp_path):
    """Test retrieving last successful commit."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)
    
    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]
    
    session_id = meta_store.begin_session(
        repo_id=repo_id,
        commit_sha="commit1",
        branch="main",
        embed_model="small"
    )
    meta_store.set_session_status(session_id, "succeeded")
    
    last_commit = meta_store.get_last_successful_commit(repo_id)
    assert last_commit == "commit1"


def test_repo_not_found(meta_store):
    """Test getting non-existent repo."""
    repo = meta_store.get_repo_by_name("nonexistent")
    assert repo is None
