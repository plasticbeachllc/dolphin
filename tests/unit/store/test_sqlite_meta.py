"""
Unit tests for SQLiteMetadataStore - Core operations

Tests basic database operations using the correct API
"""


import pytest

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
        repo_id=repo_id,
        path="src/test.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=1024
    )

    assert file_id > 0


def test_get_file_by_path(meta_store, tmp_path):
    """Test retrieving a file by path."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    meta_store.record_repo("test-repo", repo_path)

    repo = meta_store.get_repo_by_name("test-repo")
    repo_id = repo["id"]

    file_id = meta_store.upsert_file(
        repo_id=repo_id,
        path="src/test.py",
        ext=".py",
        language="python",
        is_binary=False,
        size_bytes=1024
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
