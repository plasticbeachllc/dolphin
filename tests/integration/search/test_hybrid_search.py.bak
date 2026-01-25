import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.api.app import SearchRequest
from kb.api.search_backend import create_search_backend
from kb.store.lancedb_store import LanceDBStore
from kb.store.sqlite_meta import SQLiteMetadataStore


@pytest.fixture
def hybrid_backend():
    with tempfile.TemporaryDirectory() as temp_dir:
        store_root = Path(temp_dir)
        backend = create_search_backend(store_root=store_root, hybrid_search_enabled=True)
        yield backend


@pytest.fixture
def hybrid_backend_disabled():
    with tempfile.TemporaryDirectory() as temp_dir:
        store_root = Path(temp_dir)
        backend = create_search_backend(store_root=store_root, hybrid_search_enabled=False)
        yield backend


@pytest.fixture
def populated_backend():
    """Create a backend with some test data."""
    with tempfile.TemporaryDirectory() as temp_dir:
        store_root = Path(temp_dir)

        # Create stores
        sql_store = SQLiteMetadataStore(store_root / "metadata.db")
        lance_store = LanceDBStore(store_root)

        # Initialize stores
        sql_store.initialize()

        # Add some test data to FTS5
        test_chunks = [
            {
                "content_id": "vec1",
                "repo": "test-repo",
                "path": "src/user_controller.py",
                "text_hash": "hashvec1",
                "content": "class UserController handles authentication and login functionality",
                "symbol_name": "UserController",
                "symbol_path": "controllers.UserController",
            },
            {
                "content_id": "bm251",
                "repo": "test-repo",
                "path": "src/auth_middleware.py",
                "text_hash": "hashbm251",
                "content": "middleware for JWT token validation and authentication flow",
                "symbol_name": "AuthMiddleware",
                "symbol_path": "middleware.AuthMiddleware",
            },
            {
                "content_id": "both1",
                "repo": "test-repo",
                "path": "src/auth_service.py",
                "text_hash": "hashboth1",
                "content": "UserController service for authentication and JWT validation",
                "symbol_name": "AuthService",
                "symbol_path": "services.AuthService",
            },
        ]

        sql_store.bulk_index_chunks_for_fts(test_chunks)

        # Create backend
        backend = create_search_backend(store_root=store_root, hybrid_search_enabled=True)

        # Mock the stores to use our test data
        backend.sql_store = sql_store
        backend.lance_store = lance_store

        yield backend


class TestHybridSearchBackend:
    """Test hybrid search backend creation and configuration."""

    def test_hybrid_search_enabled(self, hybrid_backend):
        """Test that hybrid search backend has hybrid search enabled."""
        assert hybrid_backend.hybrid_search_enabled is True

    def test_hybrid_search_disabled(self, hybrid_backend_disabled):
        """Test that non-hybrid backend has hybrid search disabled."""
        assert hybrid_backend_disabled.hybrid_search_enabled is False

    def test_backend_has_required_components(self, hybrid_backend):
        """Test that hybrid backend has all required components."""
        assert hasattr(hybrid_backend, "lance_store")
        assert hasattr(hybrid_backend, "sql_store")
        # Check that sql_store has bm25_search method
        assert hasattr(hybrid_backend.sql_store, "bm25_search")


class TestHybridSearchExecution:
    """Test hybrid search execution with real data."""

    def test_hybrid_search_with_data(self, populated_backend):
        """Test hybrid search with both vector and BM25 results."""
        request = SearchRequest(query="UserController", top_k=5)

        # Mock vector search to return some results
        mock_vector_results = [
            {
                "id": "vec1",
                "_distance": 0.2,
                "repo": "test-repo",
                "path": "src/user_controller.py",
            },
            {
                "id": "both1",
                "_distance": 0.3,
                "repo": "test-repo",
                "path": "src/auth_service.py",
            },
        ]

        with patch.object(populated_backend.lance_store, "query", return_value=mock_vector_results):
            results = populated_backend.search(request)

        assert isinstance(results, list)
        # Should have results from both vector and BM25 search
        assert len(results) >= 1

    def test_vector_only_search(self, populated_backend):
        """Test search when hybrid search is disabled."""
        populated_backend.hybrid_search_enabled = False
        request = SearchRequest(query="UserController", top_k=5)

        mock_vector_results = [
            {
                "id": "vec1",
                "_distance": 0.2,
                "repo": "test-repo",
                "path": "src/user_controller.py",
            },
        ]

        with patch.object(populated_backend.lance_store, "query", return_value=mock_vector_results):
            results = populated_backend.search(request)

        assert isinstance(results, list)
        assert len(results) >= 1

    def test_hybrid_search_empty_results(self, hybrid_backend):
        """Test hybrid search when both vector and BM25 return empty."""
        request = SearchRequest(query="nonexistent_query_xyz")

        with (
            patch.object(hybrid_backend.lance_store, "query", return_value=[]),
            patch.object(hybrid_backend.sql_store, "bm25_search", return_value=[]),
        ):
            results = hybrid_backend.search(request)

        assert isinstance(results, list)
        assert len(results) == 0

    def test_hybrid_search_with_score_cutoff(self, populated_backend):
        """Test hybrid search respects score cutoff."""
        request = SearchRequest(query="UserController", top_k=10, score_cutoff=0.8)

        mock_vector_results = [
            {
                "id": "high_score",
                "_distance": 0.1,
                "score": 0.9,
                "repo": "test-repo",
                "path": "test.py",
            },
            {
                "id": "low_score",
                "_distance": 0.8,
                "score": 0.5,
                "repo": "test-repo",
                "path": "test.py",
            },
        ]

        with patch.object(populated_backend.lance_store, "query", return_value=mock_vector_results):
            results = populated_backend.search(request)

        assert isinstance(results, list)
        # Should filter out low-scoring results
        for result in results:
            assert result.get("score", 0.0) >= 0.8


class TestBM25Integration:
    """Test BM25 search integration with hybrid search."""

    def test_bm25_search_finds_identifier_queries(self, populated_backend):
        """Test that BM25 finds identifier queries well."""
        request = SearchRequest(query="UserController", top_k=5)

        # Mock empty vector search, rely only on BM25
        with patch.object(populated_backend.lance_store, "query", return_value=[]):
            results = populated_backend.search(request)

        assert isinstance(results, list)
        # BM25 should find chunks containing "UserController"
        chunk_ids = [r.get("chunk_id") for r in results]
        assert "vec1" in chunk_ids or "both1" in chunk_ids

    def test_bm25_search_filters_by_repo(self, populated_backend):
        """Test BM25 search respects repository filters."""
        request = SearchRequest(query="authentication", repos=["test-repo"], top_k=5)

        # Mock vector search
        mock_vector_results = [
            {"id": "test1", "_distance": 0.3, "repo": "test-repo", "path": "test.py"},
        ]

        with patch.object(populated_backend.lance_store, "query", return_value=mock_vector_results):
            results = populated_backend.search(request)

        assert isinstance(results, list)
        # Results should be from the specified repository
        for result in results:
            if "repo" in result:
                assert result["repo"] == "test-repo"


class TestErrorHandling:
    """Test error handling in hybrid search."""

    def test_fts5_failure_fallback(self, hybrid_backend):
        """Test fallback to vector-only search when FTS5 fails."""
        request = SearchRequest(query="test")

        # Simulate an FTS error
        with (
            patch.object(
                hybrid_backend.sql_store,
                "bm25_search",
                side_effect=Exception("FTS Error"),
            ),
            patch.object(
                hybrid_backend.lance_store,
                "query",
                return_value=[{"id": "vec1", "_distance": 0.5}],
            ),
        ):
            results = hybrid_backend.search(request)
            # Should still return the vector result
            assert len(results) == 1
            assert results[0]["chunk_id"] == "vec1"

    def test_vector_search_failure_fallback(self, hybrid_backend):
        """Test fallback to BM25-only when vector search fails."""
        request = SearchRequest(query="test")

        mock_bm25_results = [{"chunk_id": "bm251", "repo": "test-repo", "path": "test.py", "score": 0.8}]

        # Simulate vector search failure
        with (
            patch.object(
                hybrid_backend.lance_store,
                "query",
                side_effect=Exception("Vector Error"),
            ),
            patch.object(hybrid_backend.sql_store, "bm25_search", return_value=mock_bm25_results),
            patch.object(hybrid_backend, "_hydrate_bm25_results", return_value=mock_bm25_results),
        ):
            results = hybrid_backend.search(request)
            # Should return BM25 results
            assert len(results) >= 1

    def test_both_searches_fail(self, hybrid_backend):
        """Test graceful handling when both searches fail."""
        request = SearchRequest(query="test")

        with (
            patch.object(
                hybrid_backend.lance_store,
                "query",
                side_effect=Exception("Vector Error"),
            ),
            patch.object(
                hybrid_backend.sql_store,
                "bm25_search",
                side_effect=Exception("FTS Error"),
            ),
        ):
            results = hybrid_backend.search(request)
            # Should return empty list, not crash
            assert isinstance(results, list)
            assert len(results) == 0


class TestSearchRequestHandling:
    """Test various SearchRequest configurations."""

    def test_different_top_k_values(self, hybrid_backend):
        """Test hybrid search with different top_k values."""
        for top_k in [1, 5, 10, 20]:
            request = SearchRequest(query="test", top_k=top_k)

            mock_results = [
                {
                    "id": f"result_{i}",
                    "_distance": 0.5 + i * 0.1,
                    "repo": "test",
                    "path": "test.py",
                }
                for i in range(top_k * 2)  # Return more than requested
            ]

            with (
                patch.object(hybrid_backend.lance_store, "query", return_value=mock_results),
                patch.object(hybrid_backend.sql_store, "bm25_search", return_value=[]),
            ):
                results = hybrid_backend.search(request)

            assert isinstance(results, list)
            # Should not return more than top_k results
            assert len(results) <= top_k

    def test_different_embed_models(self, hybrid_backend):
        """Test hybrid search with different embedding models."""
        for model in ["small", "large"]:
            request = SearchRequest(query="test", embed_model=model)

            mock_results = [{"id": "test1", "_distance": 0.5, "repo": "test", "path": "test.py"}]

            with (
                patch.object(hybrid_backend.lance_store, "query", return_value=mock_results),
                patch.object(hybrid_backend.sql_store, "bm25_search", return_value=[]),
            ):
                results = hybrid_backend.search(request)

            assert isinstance(results, list)
            assert len(results) >= 1


class TestPerformanceCharacteristics:
    """Test performance characteristics of hybrid search."""

    def test_hybrid_search_parallel_calls(self, hybrid_backend):
        """Test that hybrid search properly combines vector and BM25."""
        request = SearchRequest(query="UserController", top_k=5)

        mock_vector_results = [
            {"id": "vec1", "_distance": 0.2, "repo": "test", "path": "test.py"},
            {"id": "vec2", "_distance": 0.4, "repo": "test", "path": "test.py"},
        ]

        mock_bm25_results = [
            {"chunk_id": "bm251", "repo": "test", "path": "test.py", "score": 0.8},
            {"chunk_id": "bm252", "repo": "test", "path": "test.py", "score": 0.6},
        ]

        with (
            patch.object(hybrid_backend.lance_store, "query", return_value=mock_vector_results),
            patch.object(hybrid_backend.sql_store, "bm25_search", return_value=mock_bm25_results),
            patch.object(hybrid_backend, "_hydrate_bm25_results", return_value=mock_bm25_results),
        ):
            results = hybrid_backend.search(request)

        # Results should be fused from both sources
        assert isinstance(results, list)
        # The fused results should contain items from both searches
        result_ids = {r.get("chunk_id") or r.get("id") for r in results}
        assert len(result_ids) >= 2  # Should have multiple unique results
