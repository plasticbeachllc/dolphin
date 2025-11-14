"""Tests for LanceDB query functionality."""

import tempfile
from pathlib import Path

import pytest

from kb.store.lancedb_store import LanceDBStore


class TestLanceDBQuery:
    """Tests for LanceDB KNN search functionality."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary LanceDB store for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceDBStore(Path(tmpdir))
            store.initialize_collections()
            yield store

    def test_query_empty_table(self, temp_store):
        """Test querying an empty table returns empty results."""
        query_vector = [0.1] * 1536
        results = temp_store.query(query_vector, model="small", top_k=5)
        assert results == []

    def test_query_with_data(self, temp_store):
        """Test querying table with data returns results."""
        # Insert some test chunks
        test_chunks = [
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
                "token_count": 100,
            },
            {
                "id": "chunk2",
                "vector": [0.2] * 1536,
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 11,
                "end_line": 20,
                "text_hash": "hash2",
                "commit": "abc123",
                "branch": "main",
                "embed_model": "small",
                "token_count": 150,
            },
        ]

        temp_store.upsert_chunks("test-repo", test_chunks, model="small")

        # Query with a vector similar to first chunk
        query_vector = [0.1] * 1536
        results = temp_store.query(query_vector, model="small", top_k=2)

        assert len(results) == 2
        # Results should contain our chunk IDs
        result_ids = {r["id"] for r in results}
        assert "chunk1" in result_ids
        assert "chunk2" in result_ids

    def test_query_with_repo_filter(self, temp_store):
        """Test querying with repository filter."""
        # Insert chunks from two different repos
        repo1_chunks = [
            {
                "id": "chunk1",
                "vector": [0.1] * 1536,
                "repo": "repo1",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "text_hash": "hash1",
                "commit": "abc123",
                "branch": "main",
                "embed_model": "small",
                "token_count": 100,
            }
        ]

        repo2_chunks = [
            {
                "id": "chunk2",
                "vector": [0.1] * 1536,
                "repo": "repo2",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "text_hash": "hash2",
                "commit": "def456",
                "branch": "main",
                "embed_model": "small",
                "token_count": 100,
            }
        ]

        temp_store.upsert_chunks("repo1", repo1_chunks, model="small")
        temp_store.upsert_chunks("repo2", repo2_chunks, model="small")

        # Query filtering for repo1 only
        query_vector = [0.1] * 1536
        results = temp_store.query(query_vector, model="small", repo="repo1", top_k=10)

        assert len(results) == 1
        assert results[0]["repo"] == "repo1"
        assert results[0]["id"] == "chunk1"

    def test_query_top_k_limit(self, temp_store):
        """Test that top_k parameter limits results."""
        # Insert 10 chunks
        chunks = [
            {
                "id": f"chunk{i}",
                "vector": [float(i) / 10] * 1536,
                "repo": "test-repo",
                "path": "test.py",
                "start_line": i * 10,
                "end_line": i * 10 + 10,
                "text_hash": f"hash{i}",
                "commit": "abc123",
                "branch": "main",
                "embed_model": "small",
                "token_count": 100,
            }
            for i in range(10)
        ]

        temp_store.upsert_chunks("test-repo", chunks, model="small")

        # Query with top_k=3
        query_vector = [0.5] * 1536
        results = temp_store.query(query_vector, model="small", top_k=3)

        assert len(results) == 3

    def test_query_large_model(self, temp_store):
        """Test querying with large model."""
        # Insert chunk with large embedding
        chunks = [
            {
                "id": "chunk1",
                "vector": [0.1] * 3072,
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "text_hash": "hash1",
                "commit": "abc123",
                "branch": "main",
                "embed_model": "large",
                "token_count": 100,
            }
        ]

        temp_store.upsert_chunks("test-repo", chunks, model="large")

        # Query with large model
        query_vector = [0.1] * 3072
        results = temp_store.query(query_vector, model="large", top_k=5)

        assert len(results) == 1
        assert results[0]["id"] == "chunk1"

    def test_query_invalid_model(self, temp_store):
        """Test that invalid model raises ValueError."""
        query_vector = [0.1] * 1536

        with pytest.raises(ValueError, match="Unknown model"):
            temp_store.query(query_vector, model="invalid", top_k=5)

    def test_query_dimension_mismatch(self, temp_store):
        """Test that dimension mismatch raises ValueError."""
        # Query vector has wrong dimension for small model
        query_vector = [0.1] * 3072  # Should be 1536 for 'small'

        with pytest.raises(ValueError, match="Query vector dimension mismatch"):
            temp_store.query(query_vector, model="small", top_k=5)

    def test_query_nonexistent_table(self):
        """Test querying when table hasn't been initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LanceDBStore(Path(tmpdir))
            # Don't call initialize_collections()

            query_vector = [0.1] * 1536
            results = store.query(query_vector, model="small", top_k=5)

            # Should gracefully return empty results
            assert results == []
