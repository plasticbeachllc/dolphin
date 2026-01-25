"""
Unit tests for LanceDBStore

Tests vector store operations: initialization, upsert, delete, query
"""

import pytest
from kb.store.lancedb_store import LanceDBStore


@pytest.fixture
def temp_store(tmp_path):
    """Create a temporary LanceDB store."""
    store = LanceDBStore(tmp_path / "lancedb")
    store.initialize_collections()
    return store


@pytest.fixture
def memory_store():
    """Create an in-memory LanceDB store."""
    store = LanceDBStore("memory://test")
    store.initialize_collections()
    return store


def test_store_initialization(temp_store):
    """Test that store initializes with correct collections."""
    db = temp_store.connect()
    tables = temp_store._collect_table_names(db)
    
    assert "chunks_small" in tables
    assert "chunks_large" in tables


def test_memory_store_initialization(memory_store):
    """Test that memory store initializes correctly."""
    db = memory_store.connect()
    tables = memory_store._collect_table_names(db)
    
    assert "chunks_small" in tables
    assert "chunks_large" in tables


def test_get_schema_for_small_model(temp_store):
    """Test schema generation for small model."""
    schema = temp_store._get_schema_for_model("small")
    
    assert schema is not None
    # Check that vector field has correct dimensionality
    vector_field = next(f for f in schema if f.name == "vector")
    assert vector_field.type.list_size == 1536


def test_get_schema_for_large_model(temp_store):
    """Test schema generation for large model."""
    schema = temp_store._get_schema_for_model("large")
    
    assert schema is not None
    vector_field = next(f for f in schema if f.name == "vector")
    assert vector_field.type.list_size == 3072


def test_invalid_model_name(temp_store):
    """Test that invalid model names raise errors."""
    with pytest.raises(ValueError, match="Unknown model"):
        temp_store._get_schema_for_model("invalid")


def test_upsert_chunks_small_model(temp_store):
    """Test upserting chunks with small model."""
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
    
    temp_store.upsert_chunks("test-repo", chunks, model="small")
    
    # Verify chunk was inserted
    count = temp_store.count_repo_vectors("test-repo", model="small")
    assert count == 1


def test_delete_repo(temp_store):
    """Test deleting all vectors for a repository."""
    # First insert some chunks
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
    temp_store.upsert_chunks("test-repo", chunks, model="small")
    
    # Delete the repo
    temp_store.delete_repo("test-repo", model="small")
    
    # Verify it's deleted
    count = temp_store.count_repo_vectors("test-repo", model="small")
    assert count == 0


def test_count_repo_vectors_empty(temp_store):
    """Test counting vectors for non-existent repo."""
    count = temp_store.count_repo_vectors("nonexistent-repo", model="small")
    assert count == 0


def test_get_chunk_by_id(temp_store):
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
    temp_store.upsert_chunks("test-repo", chunks, model="small")
    
    # Retrieve by ID
    chunk = temp_store.get_chunk_by_id("chunk1", model="small")
    
    assert chunk is not None
    assert chunk["id"] == "chunk1"
    assert chunk["repo"] == "test-repo"


def test_get_chunk_by_id_not_found(temp_store):
    """Test retrieving non-existent chunk."""
    chunk = temp_store.get_chunk_by_id("nonexistent", model="small")
    assert chunk is None
