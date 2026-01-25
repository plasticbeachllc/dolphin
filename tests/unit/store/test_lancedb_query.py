"""
Tests for LanceDB store query and vector operations

Tests vector querying, filtering, and retrieval operations
"""

import pytest
from kb.store.lancedb_store import LanceDBStore


@pytest.fixture
def memory_store():
    """Create an in-memory LanceDB store."""
    store = LanceDBStore("memory://test_query")
    store.initialize_collections()
    return store


def test_query_returns_results(memory_store):
    """Test that query returns results."""
    # Insert test data
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
    
    # Query
    query_vector = [0.1] * 1536
    results = memory_store.query(query_vector, model="small", top_k=5)
    
    assert len(results) > 0


def test_query_with_repo_filter(memory_store):
    """Test querying with repository filter."""
    # Insert data for multiple repos
    for repo_name in ["repo1", "repo2"]:
        chunks = [
            {
                "id": f"{repo_name}_chunk",
                "vector": [0.1] * 1536,
                "repo": repo_name,
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "text_hash": f"hash_{repo_name}",
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
        memory_store.upsert_chunks(repo_name, chunks, model="small")
    
    # Query with filter
    query_vector = [0.1] * 1536
    results = memory_store.query(query_vector, model="small", repo="repo1", top_k=10)
    
    # All results should be from repo1
    if results:
        assert all(r.get("repo") == "repo1" for r in results)


def test_query_respects_top_k(memory_store):
    """Test that query respects top_k limit."""
    # Insert multiple chunks
    chunks = [
        {
            "id": f"chunk{i}",
            "vector": [0.1 + i * 0.01] * 1536,
            "repo": "test-repo",
            "path": f"file{i}.py",
            "start_line": 1,
            "end_line": 10,
            "text_hash": f"hash{i}",
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
        for i in range(20)
    ]
    
    memory_store.upsert_chunks("test-repo", chunks, model="small")
    
    # Query with top_k=5
    query_vector = [0.1] * 1536
    results = memory_store.query(query_vector, model="small", top_k=5)
    
    assert len(results) <= 5


def test_query_empty_store(memory_store):
    """Test querying an empty store."""
    query_vector = [0.1] * 1536
    results = memory_store.query(query_vector, model="small", top_k=5)
    
    assert results == []


def test_get_vectors_by_hashes(memory_store):
    """Test retrieving vectors by text hashes."""
    chunks = [
        {
            "id": "chunk1",
            "vector": [0.1] * 1536,
            "repo": "test-repo",
            "path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "text_hash": "unique_hash_1",
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
    
    # Get vectors by hashes
    vectors = memory_store.get_vectors_by_hashes(
        "test-repo",
        ["unique_hash_1"],
        model="small"
    )
    
    assert "unique_hash_1" in vectors
    assert len(vectors["unique_hash_1"]) == 1536


def test_upsert_replaces_existing(memory_store):
    """Test that upsert replaces existing chunks."""
    chunks_v1 = [
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
    
    memory_store.upsert_chunks("test-repo", chunks_v1, model="small")
    
    # Update with new vector
    chunks_v2 = [
        {
            "id": "chunk1",
            "vector": [0.9] * 1536,  # Different vector
            "repo": "test-repo",
            "path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "text_hash": "hash1_updated",
            "commit": "def456",
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
    
    memory_store.upsert_chunks("test-repo", chunks_v2, model="small")
    
    # Should only have one chunk
    count = memory_store.count_repo_vectors("test-repo", model="small")
    assert count == 1
    
    # Verify it's the updated version
    chunk = memory_store.get_chunk_by_id("chunk1", model="small")
    assert chunk["text_hash"] == "hash1_updated"
