import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from kb.api.search_backend import KnowledgeSearchBackend, create_search_backend
from kb.api.app import SearchRequest
from kb.config import KBConfig
import math

@pytest.fixture
def mock_providers():
    """Provides mock stores and providers for the search backend."""
    embedding_provider = MagicMock(spec=["embed_texts"])
    lance_store = MagicMock(spec=["query", "upsert_chunks"])
    sql_store = MagicMock(spec=["bm25_search", "get_chunk_contents", "get_chunk_by_id", "index_chunk_for_fts"])
    return embedding_provider, lance_store, sql_store

@pytest.fixture
def basic_backend(mock_providers):
    """A basic backend with hybrid search enabled."""
    embedding_provider, lance_store, sql_store = mock_providers
    return KnowledgeSearchBackend(
        embedding_provider, lance_store, sql_store, hybrid_search_enabled=True
    )

class TestKnowledgeSearchBackend:
    def test_search_basic_hybrid(self, basic_backend):
        """Test that hybrid search correctly fuses vector and BM25 results."""
        embedding_provider, lance_store, sql_store = basic_backend.embedding_provider, basic_backend.lance_store, basic_backend.sql_store

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        lance_store.query.return_value = [{"id": "chunk1", "_distance": 0.2, "repo": "test", "path": "p1.py"}]
        # `reciprocal_rank_fusion` expects the `id_field` to be 'chunk_id'
        sql_store.bm25_search.return_value = [{"chunk_id": "chunk2", "score": 25.0, "repo": "test", "path": "p2.py"}]
        # Mock the hydration call for the BM25 result
        sql_store.get_chunk_by_id.return_value = {"path": "p2.py", "chunk_id": "chunk2"}

        request = SearchRequest(query="test", top_k=10)
        results = basic_backend.search(request)
        
        assert len(results) == 2
        assert {r["chunk_id"] for r in results} == {"chunk1", "chunk2"}
        assert "score" in results[0]
        assert results[0]['score'] > 0

    def test_search_with_score_cutoff(self, basic_backend):
        """Test that the score_cutoff is applied after score normalization and fusion."""
        embedding_provider, lance_store, sql_store = basic_backend.embedding_provider, basic_backend.lance_store, basic_backend.sql_store
        
        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        # This result will have a similarity score of 1 / (1 + 0.1) = ~0.9, so it should be kept.
        lance_store.query.return_value = [{"id": "chunk1", "_distance": 0.1, "repo": "repo", "path": "test.py"}]
        # This result has a negative score, its normalized score will be very low and it should be filtered.
        sql_store.bm25_search.return_value = [{"chunk_id": "chunk2", "score": -10.0, "repo": "repo", "path": "test.py"}]
        sql_store.get_chunk_by_id.return_value = {"path": "test.py", "chunk_id": "chunk2"}

        request = SearchRequest(query="test", score_cutoff=0.5)
        results = basic_backend.search(request)
        
        assert len(results) == 1
        assert results[0]['chunk_id'] == 'chunk1'

@pytest.fixture
def real_backend(tmp_path: Path):
    """Provides a backend with real stores for integration testing."""
    return create_search_backend(store_root=tmp_path, embedding_provider_type="stub")

class TestSearchBackendIntegration:
    def test_end_to_end_search_flow(self, real_backend: KnowledgeSearchBackend):
        """Test a full search cycle from indexing to retrieval."""
        chunks_to_upsert = [{"id": "chunk1", "vector": [0.1] * 1536, "repo": "test-repo", "path": "test.py"}]
        real_backend.lance_store.upsert_chunks("test-repo", chunks_to_upsert, model="small")
        real_backend.sql_store.index_chunk_for_fts(
            content_id="chunk1", repo="test-repo", path="test.py", content="some test content"
        )
        
        request = SearchRequest(query="test", top_k=5, embed_model="small")
        results = real_backend.search(request)
        
        assert len(results) >= 1
        assert "score" in results[0]
        assert results[0]["chunk_id"] == "chunk1"