"""
Tests for LanceDB store operations

Tests basic store operations without fragile table name assertions
"""

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
