"""Unit tests for parallel hybrid search."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from kb.search.parallel_search import (
    ParallelHybridSearch,
    SearchResult,
    reciprocal_rank_fusion,
)


class TestReciprocalRankFusion:
    """Unit tests for RRF algorithm."""

    def test_rrf_empty_results(self):
        """Test RRF with empty results."""
        result = reciprocal_rank_fusion([], [])
        assert result == []

    def test_rrf_single_list(self):
        """Test RRF with single result list."""
        results1 = [
            SearchResult(id="1", score=0.9, text="test1"),
            SearchResult(id="2", score=0.8, text="test2"),
        ]

        merged = reciprocal_rank_fusion([results1], k=60)

        assert len(merged) == 2
        assert merged[0].id == "1"
        assert merged[1].id == "2"

    def test_rrf_two_lists(self):
        """Test RRF with two result lists."""
        results1 = [
            SearchResult(id="1", score=0.9, text="doc1"),
            SearchResult(id="2", score=0.7, text="doc2"),
        ]
        results2 = [
            SearchResult(id="2", score=0.95, text="doc2"),
            SearchResult(id="3", score=0.8, text="doc3"),
        ]

        merged = reciprocal_rank_fusion([results1, results2], k=60)

        # Doc2 appears in both lists, should rank highest
        assert len(merged) == 3
        assert merged[0].id == "2"  # Highest RRF score

    def test_rrf_preserves_metadata(self):
        """Test that RRF preserves result metadata."""
        results1 = [
            SearchResult(
                id="1",
                score=0.9,
                text="test",
                repo="repo1",
                path="file.py",
                start_line=1,
                end_line=10,
            )
        ]

        merged = reciprocal_rank_fusion([results1])

        assert merged[0].repo == "repo1"
        assert merged[0].path == "file.py"
        assert merged[0].start_line == 1
        assert merged[0].end_line == 10

    def test_rrf_k_parameter(self):
        """Test that k parameter affects scoring."""
        results1 = [SearchResult(id="1", score=1.0, text="test")]

        # Different k values should produce different RRF scores
        merged_k60 = reciprocal_rank_fusion([results1], k=60)
        merged_k100 = reciprocal_rank_fusion([results1], k=100)

        # Scores will be different due to k parameter
        assert merged_k60[0].score != merged_k100[0].score


class TestParallelHybridSearch:
    """Unit tests for ParallelHybridSearch class."""

    @pytest.fixture
    def mock_stores(self):
        """Create mock stores for testing."""
        vector_store = Mock()
        bm25_store = Mock()
        embedding_provider = Mock()

        return vector_store, bm25_store, embedding_provider

    @pytest.fixture
    def search_engine(self, mock_stores):
        """Create ParallelHybridSearch instance."""
        vector_store, bm25_store, embedding_provider = mock_stores

        return ParallelHybridSearch(
            vector_store=vector_store,
            bm25_store=bm25_store,
            embedding_provider=embedding_provider,
        )

    @pytest.mark.asyncio
    async def test_search_async_basic(self, search_engine, mock_stores):
        """Test basic async search."""
        vector_store, bm25_store, embedding_provider = mock_stores

        # Mock embedding generation
        embedding_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)

        # Mock vector search results
        vector_store.query = Mock(return_value=[
            {"id": "1", "text": "result1", "repo": "repo1", "path": "file1.py",
             "start_line": 1, "end_line": 10, "_distance": 0.1}
        ])

        # Mock BM25 search results
        bm25_store.search = Mock(return_value=[
            {"chunk_id": "2", "content": "result2", "repo": "repo1", "file_path": "file2.py",
             "start_line": 1, "end_line": 10, "score": 5.0}
        ])

        # Execute search
        results = await search_engine.search_async(
            query="test query",
            top_k=10,
        )

        # Should have results from both searches
        assert len(results) > 0
        assert embedding_provider.embed_query.called

    @pytest.mark.asyncio
    async def test_search_async_with_existing_embedding(self, search_engine, mock_stores):
        """Test search with pre-computed embedding."""
        vector_store, bm25_store, _ = mock_stores

        query_embedding = [0.1] * 1536

        vector_store.query = Mock(return_value=[])
        bm25_store.search = Mock(return_value=[])

        results = await search_engine.search_async(
            query="test",
            query_embedding=query_embedding,
            top_k=10,
        )

        # Should not call embedding provider
        assert results is not None

    @pytest.mark.asyncio
    async def test_search_async_with_repo_filter(self, search_engine, mock_stores):
        """Test search with repository filter."""
        vector_store, bm25_store, embedding_provider = mock_stores

        embedding_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)
        vector_store.query = Mock(return_value=[])
        bm25_store.search = Mock(return_value=[])

        await search_engine.search_async(
            query="test",
            top_k=10,
            repo="test_repo",
        )

        # Verify repo filter was passed
        vector_store.query.assert_called_once()
        call_kwargs = vector_store.query.call_args[1]
        assert call_kwargs.get("repo") == "test_repo"

    @pytest.mark.asyncio
    async def test_search_async_fallback_on_error(self, search_engine, mock_stores):
        """Test fallback to sequential search on error."""
        vector_store, bm25_store, embedding_provider = mock_stores

        embedding_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)

        # Simulate error in parallel execution
        vector_store.query = Mock(side_effect=RuntimeError("Test error"))
        bm25_store.search = Mock(return_value=[])

        # Should fall back to sequential and handle error gracefully
        results = await search_engine.search_async(
            query="test",
            top_k=10,
        )

        # Should return empty results rather than crashing
        assert results == []

    def test_search_sync(self, search_engine, mock_stores):
        """Test synchronous search wrapper."""
        vector_store, bm25_store, embedding_provider = mock_stores

        embedding_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)
        vector_store.query = Mock(return_value=[])
        bm25_store.search = Mock(return_value=[])

        # Should run async search in event loop
        results = search_engine.search(query="test", top_k=10)

        assert results is not None

    @pytest.mark.asyncio
    async def test_vector_weight_adjustment(self, search_engine, mock_stores):
        """Test vector search weight adjustment."""
        vector_store, bm25_store, embedding_provider = mock_stores

        # Create search engine with custom weights
        custom_engine = ParallelHybridSearch(
            vector_store=vector_store,
            bm25_store=bm25_store,
            embedding_provider=embedding_provider,
            vector_weight=0.7,  # Higher weight for vector search
        )

        embedding_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)
        vector_store.query = Mock(return_value=[
            {"id": "1", "text": "test", "repo": "r", "path": "f",
             "start_line": 1, "end_line": 1, "_distance": 0.1}
        ])
        bm25_store.search = Mock(return_value=[])

        results = await custom_engine.search_async(query="test", top_k=10)

        # Should complete successfully
        assert results is not None

    @pytest.mark.asyncio
    async def test_empty_query(self, search_engine, mock_stores):
        """Test search with empty query."""
        _, _, embedding_provider = mock_stores

        embedding_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)

        # Empty query should still work
        results = await search_engine.search_async(query="", top_k=10)

        assert results is not None

    def test_get_stats(self, search_engine):
        """Test statistics retrieval."""
        stats = search_engine.get_stats()

        assert 'total_searches' in stats
        assert 'avg_vector_time_ms' in stats
        assert 'avg_bm25_time_ms' in stats
        assert 'avg_total_time_ms' in stats
        assert 'parallel_speedup' in stats

    @pytest.mark.asyncio
    async def test_result_deduplication(self, search_engine, mock_stores):
        """Test that duplicate results are properly handled."""
        vector_store, bm25_store, embedding_provider = mock_stores

        embedding_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)

        # Return same ID from both searches
        vector_store.query = Mock(return_value=[
            {"id": "1", "text": "test", "repo": "r", "path": "f",
             "start_line": 1, "end_line": 10, "_distance": 0.1}
        ])

        bm25_store.search = Mock(return_value=[
            {"chunk_id": "1", "content": "test", "repo": "r", "file_path": "f",
             "start_line": 1, "end_line": 10, "score": 5.0}
        ])

        results = await search_engine.search_async(query="test", top_k=10)

        # RRF should merge duplicate IDs
        ids = [r.id for r in results]
        assert len(ids) == len(set(ids))  # No duplicate IDs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
