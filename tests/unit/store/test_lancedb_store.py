"""
Tests for LanceDB store operations

Tests basic store operations without fragile table name assertions
"""

from unittest.mock import MagicMock

import pytest

from kb.store.lancedb_store import LanceDBStore


@pytest.fixture
def memory_store():
    """Create an in-memory LanceDB store."""
    store = LanceDBStore("memory://test_basic")
    store.initialize_collections()
    return store


def test_store_initializes(memory_store):
    """Test that store initializes without errors."""
    assert memory_store is not None


def test_upsert_and_count(memory_store):
    """Test upserting chunks and counting."""
    chunks = [
        {
            "id": "chunk1",
            "vector": [0.1] * 1536,
            "repo": "test-repo",
            "path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "text_hash": "hash1",
            "commit": "abc123",
            "branch": "main",
            "embed_model": "small",
            "language": "python",
            "symbol_kind": None,
            "symbol_name": None,
            "symbol_path": None,
            "heading_h1": None,
            "heading_h2": None,
            "heading_h3": None,
            "token_count": 100,
            "created_at": None,
        }
    ]

    memory_store.upsert_chunks("test-repo", chunks, model="small")
    count = memory_store.count_repo_vectors("test-repo", model="small")
    assert count == 1


def test_delete_repo(memory_store):
    """Test deleting all vectors for a repository."""
    chunks = [
        {
            "id": "chunk1",
            "vector": [0.1] * 1536,
            "repo": "test-repo",
            "path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "text_hash": "hash1",
            "commit": "abc123",
            "branch": "main",
            "embed_model": "small",
            "language": None,
            "symbol_kind": None,
            "symbol_name": None,
            "symbol_path": None,
            "heading_h1": None,
            "heading_h2": None,
            "heading_h3": None,
            "token_count": 100,
            "created_at": None,
        }
    ]
    memory_store.upsert_chunks("test-repo", chunks, model="small")
    memory_store.delete_repo("test-repo", model="small")
    count = memory_store.count_repo_vectors("test-repo", model="small")
    assert count == 0


def test_get_chunk_by_id(memory_store):
    """Test retrieving a chunk by ID."""
    chunks = [
        {
            "id": "chunk1",
            "vector": [0.1] * 1536,
            "repo": "test-repo",
            "path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "text_hash": "hash1",
            "commit": "abc123",
            "branch": "main",
            "embed_model": "small",
            "language": "python",
            "symbol_kind": None,
            "symbol_name": None,
            "symbol_path": None,
            "heading_h1": None,
            "heading_h2": None,
            "heading_h3": None,
            "token_count": 100,
            "created_at": None,
        }
    ]
    memory_store.upsert_chunks("test-repo", chunks, model="small")
    chunk = memory_store.get_chunk_by_id("chunk1", model="small")
    assert chunk is not None
    assert chunk["id"] == "chunk1"


def test_query_builds_index_once_per_table():
    """Index creation should be attempted once and then cached."""
    store = LanceDBStore("memory://test_index_once")

    mock_search_query = MagicMock()
    mock_search_query.limit.return_value = mock_search_query
    mock_search_query.metric.return_value = mock_search_query
    mock_search_query.nprobes.return_value = mock_search_query
    mock_search_query.refine_factor.return_value = mock_search_query
    mock_search_query.to_list.return_value = []

    mock_table = MagicMock()
    mock_table.count_rows.return_value = 1
    mock_table.list_indices.return_value = []
    mock_table.search.return_value = mock_search_query

    mock_db = MagicMock()
    mock_db.open_table.return_value = mock_table
    store._db = mock_db

    query_vector = [0.1] * 1536
    store.query(query_vector, model="small", top_k=1)
    store.query(query_vector, model="small", top_k=1)

    assert mock_table.create_index.call_count == 1


def test_connect_called_once_under_concurrent_threads():
    """Spin up 10 threads all calling connect() simultaneously; underlying lancedb.connect called exactly once."""
    import threading

    store = LanceDBStore("memory://test_concurrent")

    mock_db = MagicMock()

    with pytest.importorskip("unittest.mock").patch("lancedb.connect") as mock_lancedb_connect:
        mock_lancedb_connect.return_value = mock_db

        barrier = threading.Barrier(10)
        results = []

        def worker():
            barrier.wait()
            db = store.connect()
            results.append(db)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same db object
        assert all(r is mock_db for r in results)
        # lancedb.connect should only be called once
        assert mock_lancedb_connect.call_count == 1


def test_connect_returns_same_db_object_on_second_call():
    """Two sequential calls to connect() return the same object (is identity)."""
    store = LanceDBStore("memory://test_same_obj")

    with pytest.importorskip("unittest.mock").patch("lancedb.connect") as mock_lancedb_connect:
        mock_db = MagicMock()
        mock_lancedb_connect.return_value = mock_db

        db1 = store.connect()
        db2 = store.connect()

        assert db1 is db2
        assert mock_lancedb_connect.call_count == 1


def test_connect_creates_directory_if_missing(tmp_path):
    """Store root does not exist; connect() creates it via mkdir."""
    store_root = tmp_path / "nonexistent" / "deep" / "path"
    assert not store_root.exists()

    store = LanceDBStore(store_root)

    with pytest.importorskip("unittest.mock").patch("lancedb.connect") as mock_lancedb_connect:
        mock_lancedb_connect.return_value = MagicMock()
        store.connect()

    assert store_root.exists()
