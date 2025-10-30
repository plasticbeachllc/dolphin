"""Tests for search backend implementation."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pb_kb.api.app import SearchRequest
from pb_kb.api.search_backend import KnowledgeSearchBackend, create_search_backend
from pb_kb.embeddings.provider import EmbeddingProvider
from pb_kb.store.lancedb_store import LanceDBStore
from pb_kb.store.sqlite_meta import SQLiteMetadataStore


class TestKnowledgeSearchBackend:
    """Tests for KnowledgeSearchBackend."""

    @pytest.fixture
    def mock_providers(self):
        """Create mock providers for testing."""
        embedding_provider = Mock(spec=EmbeddingProvider)
        lance_store = Mock(spec=LanceDBStore)
        sql_store = Mock(spec=SQLiteMetadataStore)
        return embedding_provider, lance_store, sql_store

    def test_search_basic(self, mock_providers):
        """Test basic search flow."""
        embedding_provider, lance_store, sql_store = mock_providers

        # Mock embedding provider to return a query embedding
        embedding_provider.embed_texts.return_value = [[0.1] * 1536]

        # Mock LanceDB to return search results
        lance_store.query.return_value = [
            {
                "id": "chunk1",
                "repo": "test-repo",
                "path": "src/main.py",
                "start_line": 1,
                "end_line": 10,
                "language": "python",
                "symbol_kind": "function",
                "symbol_name": "main",
                "symbol_path": "main",
                "commit": "abc123",
                "branch": "main",
                "_distance": 0.5,
            }
        ]

        # Create backend
        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store)

        # Execute search
        request = SearchRequest(query="test query", top_k=10, embed_model="small")
        results = backend.search(request)

        # Verify embedding was called correctly
        embedding_provider.embed_texts.assert_called_once_with("small", ["test query"])

        # Verify LanceDB search was called
        lance_store.query.assert_called_once()
        call_args = lance_store.query.call_args
        assert len(call_args[0][0]) == 1536  # Query vector
        assert call_args[1]["model"] == "small"
        assert call_args[1]["top_k"] == 10

        # Verify results
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk1"
        assert results[0]["repo"] == "test-repo"
        assert results[0]["path"] == "src/main.py"
        assert results[0]["symbol_name"] == "main"
        assert 0 < results[0]["score"] <= 1.0

    def test_search_with_repo_filter(self, mock_providers):
        """Test search with single repo filter."""
        embedding_provider, lance_store, sql_store = mock_providers

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        lance_store.query.return_value = []

        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store)

        # Search with repo filter
        request = SearchRequest(
            query="test", repos=["specific-repo"], embed_model="small"
        )
        backend.search(request)

        # Verify repo filter was passed to LanceDB
        lance_store.query.assert_called_once()
        assert lance_store.query.call_args[1]["repo"] == "specific-repo"

    def test_search_with_multiple_repos(self, mock_providers):
        """Test search with multiple repo filters (post-filter)."""
        embedding_provider, lance_store, sql_store = mock_providers

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        lance_store.query.return_value = [
            {
                "id": "chunk1",
                "repo": "repo1",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.5,
            },
            {
                "id": "chunk2",
                "repo": "repo2",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.6,
            },
            {
                "id": "chunk3",
                "repo": "repo3",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.7,
            },
        ]

        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store)

        # Search with multiple repos
        request = SearchRequest(
            query="test", repos=["repo1", "repo2"], embed_model="small"
        )
        results = backend.search(request)

        # Should filter to only repo1 and repo2
        assert len(results) == 2
        assert {r["repo"] for r in results} == {"repo1", "repo2"}

    def test_search_with_path_prefix(self, mock_providers):
        """Test search with path prefix filter."""
        embedding_provider, lance_store, sql_store = mock_providers

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        lance_store.query.return_value = [
            {
                "id": "chunk1",
                "repo": "repo",
                "path": "src/main.py",
                "start_line": 1,
                "end_line": 10,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.5,
            },
            {
                "id": "chunk2",
                "repo": "repo",
                "path": "tests/test_main.py",
                "start_line": 1,
                "end_line": 10,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.6,
            },
            {
                "id": "chunk3",
                "repo": "repo",
                "path": "docs/readme.md",
                "start_line": 1,
                "end_line": 10,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.7,
            },
        ]

        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store)

        # Filter for only "src/" paths
        request = SearchRequest(
            query="test", path_prefix=["src/"], embed_model="small"
        )
        results = backend.search(request)

        assert len(results) == 1
        assert results[0]["path"] == "src/main.py"

    def test_search_with_score_cutoff(self, mock_providers):
        """Test search with score cutoff filter."""
        embedding_provider, lance_store, sql_store = mock_providers

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        lance_store.query.return_value = [
            {
                "id": "chunk1",
                "repo": "repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.1,  # High similarity
            },
            {
                "id": "chunk2",
                "repo": "repo",
                "path": "test.py",
                "start_line": 11,
                "end_line": 20,
                "commit": "abc",
                "branch": "main",
                "_distance": 0.9,  # Low similarity
            },
        ]

        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store)

        # Set score cutoff to filter low-similarity results
        request = SearchRequest(
            query="test", score_cutoff=0.5, embed_model="small"
        )
        results = backend.search(request)

        # Only high-similarity result should pass
        # distance <= (1.0 - 0.5) = 0.5
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk1"

    def test_search_large_model(self, mock_providers):
        """Test search with large embedding model."""
        embedding_provider, lance_store, sql_store = mock_providers

        embedding_provider.embed_texts.return_value = [[0.1] * 3072]
        lance_store.query.return_value = []

        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store)

        request = SearchRequest(query="test", embed_model="large", top_k=5)
        backend.search(request)

        # Verify large model was used
        embedding_provider.embed_texts.assert_called_once_with("large", ["test"])
        assert lance_store.query.call_args[1]["model"] == "large"

    def test_distance_to_similarity_conversion(self):
        """Test distance to similarity score conversion."""
        backend = KnowledgeSearchBackend(Mock(), Mock(), Mock())

        # Distance 0 should give similarity 1.0
        assert backend._distance_to_similarity(0.0) == 1.0

        # Distance 1 should give similarity 0.5
        assert backend._distance_to_similarity(1.0) == 0.5

        # Large distance should give low similarity
        assert backend._distance_to_similarity(10.0) < 0.1


class TestSearchBackendFactory:
    """Tests for create_search_backend factory."""

    def test_create_backend_with_stub_provider(self):
        """Test creating backend with stub embedding provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir)

            backend = create_search_backend(store_root, embedding_provider_type="stub")

            assert isinstance(backend, KnowledgeSearchBackend)
            assert isinstance(backend.embedding_provider, EmbeddingProvider)
            assert isinstance(backend.lance_store, LanceDBStore)
            assert isinstance(backend.sql_store, SQLiteMetadataStore)

    def test_create_backend_with_openai_provider(self):
        """Test creating backend with OpenAI embedding provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir)

            with patch("openai.OpenAI"):
                backend = create_search_backend(
                    store_root,
                    embedding_provider_type="openai",
                    api_key="test-key",
                )

                assert isinstance(backend, KnowledgeSearchBackend)
                # Verify it's an OpenAI provider (not stub)
                assert backend.embedding_provider.__class__.__name__ == "OpenAIEmbeddingProvider"


class TestSearchBackendIntegration:
    """Integration tests with real stores."""

    @pytest.fixture
    def real_backend(self):
        """Create a real backend with stub provider for integration testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir)
            backend = create_search_backend(store_root, embedding_provider_type="stub")

            # Initialize stores
            backend.lance_store.initialize_collections()
            backend.sql_store.initialize()

            yield backend

    def test_end_to_end_search_flow(self, real_backend):
        """Test complete search flow with real stores."""
        # Insert test data
        chunks = [
            {
                "id": "chunk1",
                "vector": [0.1] * 1536,
                "repo": "test-repo",
                "path": "src/main.py",
                "start_line": 1,
                "end_line": 10,
                "text_hash": "hash1",
                "commit": "abc123",
                "branch": "main",
                "embed_model": "small",
                "language": "python",
                "symbol_kind": "function",
                "symbol_name": "main",
                "symbol_path": "main",
                "token_count": 100,
            }
        ]

        real_backend.lance_store.upsert_chunks("test-repo", chunks, model="small")

        # Execute search
        request = SearchRequest(query="test query", top_k=5, embed_model="small")
        results = real_backend.search(request)

        # Verify results
        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk1"
        assert results[0]["repo"] == "test-repo"
        assert results[0]["path"] == "src/main.py"
        assert results[0]["symbol_name"] == "main"
        assert results[0]["score"] > 0
