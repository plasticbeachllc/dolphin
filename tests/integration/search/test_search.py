"""Integration tests for search functionality."""

from pathlib import Path
from typing import Any

import pytest

from kb.api.app import SearchRequest, reset_search_backend, reset_stores, set_search_backend, set_stores
from kb.store import LanceDBStore, SQLiteMetadataStore
from tests.utils.mock_services import MockEmbeddingService


class MockSearchBackend:
    """Mock search backend for integration testing."""

    def __init__(self, metadata_store: SQLiteMetadataStore, lancedb_store: LanceDBStore):
        self.metadata_store = metadata_store
        self.lancedb_store = lancedb_store
        self.search_calls = []

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        """Mock search implementation that returns predictable results."""
        self.search_calls.append(request)

        # Return mock search results based on query
        if "widget" in request.query.lower():
            return [
                {
                    "path": "src/widgets.py",
                    "start_line": 1,
                    "end_line": 10,
                    "text": "class Widget: ...",
                    "score": 0.95,
                    "language": "python",
                    "symbol_name": "Widget",
                    "symbol_kind": "class",
                }
            ]
        elif "overview" in request.query.lower():
            return [
                {
                    "path": "docs/overview.md",
                    "start_line": 1,
                    "end_line": 5,
                    "text": "# Overview\n\nThis is the project overview.",
                    "score": 0.88,
                    "language": "markdown",
                    "heading_h1": "Overview",
                }
            ]
        else:
            return []


class TestSearchIntegration:
    """Integration tests for search functionality."""

    def setup_method(self):
        """Set up test environment."""
        reset_search_backend()
        reset_stores()

    def teardown_method(self):
        """Clean up test environment."""
        reset_search_backend()
        reset_stores()

    @pytest.mark.asyncio
    async def test_search_basic_functionality(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test basic search functionality with mock backend."""
        # Setup
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")

        # Create and set mock search backend
        mock_backend = MockSearchBackend(metadata_store, lancedb_store)
        set_search_backend(mock_backend)
        set_stores(metadata_store, lancedb_store)

        # Register repo used in test
        metadata_store.initialize()
        metadata_store.record_repo("test-repo", str(sample_repo_path), default_embed_model="small")

        # Test search with widget query
        request = SearchRequest(query="widget class", repos=["test-repo"], top_k=5, embed_model="small")

        from kb.api.app import search

        response = await search(request)

        # Verify response structure
        assert "hits" in response
        assert "meta" in response
        assert response["meta"]["top_k"] == 5
        assert response["meta"]["model"] == "small"

        # Verify search results
        hits = response["hits"]
        assert len(hits) == 1
        assert hits[0]["path"] == "src/widgets.py"
        assert hits[0]["language"] == "python"
        assert "Widget" in hits[0]["text"]

    @pytest.mark.asyncio
    async def test_search_with_filters(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test search with repository and path filters."""
        # Setup
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")

        # Create and set mock search backend
        mock_backend = MockSearchBackend(metadata_store, lancedb_store)
        set_search_backend(mock_backend)
        set_stores(metadata_store, lancedb_store)

        # Register repo used in test
        metadata_store.initialize()
        metadata_store.record_repo("specific-repo", str(sample_repo_path), default_embed_model="small")

        # Test search with repository filter
        request = SearchRequest(
            query="overview",
            repos=["specific-repo"],
            path_prefix=["docs/"],
            top_k=3,
            embed_model="small",
        )

        from kb.api.app import search

        response = await search(request)

        # Verify response
        hits = response["hits"]
        assert len(hits) == 1
        assert hits[0]["path"] == "docs/overview.md"
        assert hits[0]["language"] == "markdown"

    @pytest.mark.asyncio
    async def test_search_empty_results(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test search with no matching results."""
        # Setup
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")

        # Create and set mock search backend
        mock_backend = MockSearchBackend(metadata_store, lancedb_store)
        set_search_backend(mock_backend)
        set_stores(metadata_store, lancedb_store)

        # Register repo used in test
        metadata_store.initialize()
        metadata_store.record_repo("test-repo", str(sample_repo_path), default_embed_model="small")

        # Test search with no matches
        request = SearchRequest(query="nonexistent term", repos=["test-repo"], top_k=5, embed_model="small")

        from kb.api.app import search

        response = await search(request)

        # Verify empty results
        assert len(response["hits"]) == 0
        assert response["meta"]["top_k"] == 5

    @pytest.mark.asyncio
    async def test_search_latency_measurement(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test that search latency is properly measured."""
        # Setup
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")

        # Create and set mock search backend
        mock_backend = MockSearchBackend(metadata_store, lancedb_store)
        set_search_backend(mock_backend)
        set_stores(metadata_store, lancedb_store)

        # Register repo used in test
        metadata_store.initialize()
        metadata_store.record_repo("test-repo", str(sample_repo_path), default_embed_model="small")

        # Test search
        request = SearchRequest(query="widget", repos=["test-repo"], top_k=5, embed_model="small")

        from kb.api.app import search

        response = await search(request)

        # Verify latency measurement
        assert "latency_ms" in response["meta"]
        latency = response["meta"]["latency_ms"]
        assert isinstance(latency, int)
        assert latency >= 0

    def test_search_backend_configuration(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test search backend configuration and lifecycle."""
        from kb.api.app import get_search_backend, reset_search_backend, set_search_backend

        # Get default backend
        default_backend = get_search_backend()

        # Create and set custom backend
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")
        custom_backend = MockSearchBackend(metadata_store, lancedb_store)

        set_search_backend(custom_backend)
        assert get_search_backend() == custom_backend

        # Reset to default
        reset_search_backend()
        assert get_search_backend() == default_backend

    @pytest.mark.asyncio
    async def test_search_multiple_repositories(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test search across multiple repositories."""
        # Setup
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")

        # Create and set mock search backend
        mock_backend = MockSearchBackend(metadata_store, lancedb_store)
        set_search_backend(mock_backend)
        set_stores(metadata_store, lancedb_store)

        # Register repos used in test
        metadata_store.initialize()
        metadata_store.record_repo("repo1", str(sample_repo_path / "repo1"), default_embed_model="small")
        metadata_store.record_repo("repo2", str(sample_repo_path / "repo2"), default_embed_model="small")
        metadata_store.record_repo("repo3", str(sample_repo_path / "repo3"), default_embed_model="small")

        # Test search with multiple repositories
        request = SearchRequest(
            query="widget",
            repos=["repo1", "repo2", "repo3"],
            top_k=10,
            embed_model="small",
        )

        from kb.api.app import search

        await search(request)

        # Verify backend received correct repositories
        assert len(mock_backend.search_calls) == 1
        search_call = mock_backend.search_calls[0]
        assert search_call.repos == ["repo1", "repo2", "repo3"]
        assert search_call.top_k == 10


class TestSearchPerformance:
    """Performance-focused search integration tests."""

    @pytest.mark.asyncio
    async def test_search_response_time(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test that search responses meet performance targets."""
        import time

        # Setup
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")

        # Create and set mock search backend
        mock_backend = MockSearchBackend(metadata_store, lancedb_store)
        set_search_backend(mock_backend)
        set_stores(metadata_store, lancedb_store)

        # Register repo used in test
        metadata_store.initialize()
        metadata_store.record_repo("test-repo", str(sample_repo_path), default_embed_model="small")

        # Measure search performance
        request = SearchRequest(query="test query", repos=["test-repo"], top_k=5, embed_model="small")

        from kb.api.app import search

        start_time = time.time()
        response = await search(request)
        end_time = time.time()

        response_time_ms = (end_time - start_time) * 1000

        # Verify response time is reasonable (under 100ms for mock)
        assert response_time_ms < 100
        assert response["meta"]["latency_ms"] < 100

    @pytest.mark.asyncio
    async def test_search_concurrent_requests(
        self,
        sample_repo_path: Path,
        temp_db_path: Path,
        mock_embedding_service: MockEmbeddingService,
    ):
        """Test search performance under concurrent load."""
        import asyncio
        import time

        # Setup
        metadata_store = SQLiteMetadataStore(str(temp_db_path))
        lancedb_store = LanceDBStore("memory://test_db")

        # Create and set mock search backend
        mock_backend = MockSearchBackend(metadata_store, lancedb_store)
        set_search_backend(mock_backend)
        set_stores(metadata_store, lancedb_store)

        # Register repos used in test
        metadata_store.initialize()
        for i in range(10):
             metadata_store.record_repo(f"repo-{i}", str(sample_repo_path), default_embed_model="small")

        from kb.api.app import search

        # Create multiple search requests
        requests = [
            SearchRequest(
                query=f"query {i}",
                repos=[f"repo-{i % 3}"],
                top_k=5,
                embed_model="small",
            )
            for i in range(10)
        ]

        # Run concurrent searches
        start_time = time.time()
        tasks = [search(request) for request in requests]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        total_time_ms = (end_time - start_time) * 1000

        # Verify all searches completed
        assert len(results) == 10
        for result in results:
            assert "hits" in result
            assert "meta" in result

        # Verify reasonable performance for concurrent requests
        # (should be much faster than sequential execution)
        assert total_time_ms < 500  # All 10 requests should complete in under 500ms
