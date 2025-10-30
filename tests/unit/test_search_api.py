"""End-to-end tests for the search API."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pb_kb.api.app import app, set_search_backend, reset_search_backend
from pb_kb.api.search_backend import create_search_backend


class TestSearchAPI:
    """Tests for /v1/search API endpoint."""

    @pytest.fixture
    def client_with_backend(self):
        """Create a test client with a real search backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir)

            # Create backend with stub provider
            backend = create_search_backend(store_root, embedding_provider_type="stub")

            # Initialize stores
            backend.lance_store.initialize_collections()
            backend.sql_store.initialize()

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
                },
                {
                    "id": "chunk2",
                    "vector": [0.2] * 1536,
                    "repo": "test-repo",
                    "path": "src/utils.py",
                    "start_line": 1,
                    "end_line": 15,
                    "text_hash": "hash2",
                    "commit": "abc123",
                    "branch": "main",
                    "embed_model": "small",
                    "language": "python",
                    "symbol_kind": "function",
                    "symbol_name": "helper",
                    "symbol_path": "helper",
                    "token_count": 120,
                },
            ]

            backend.lance_store.upsert_chunks("test-repo", chunks, model="small")

            # Set backend for API
            set_search_backend(backend)

            # Create test client
            client = TestClient(app)

            yield client

            # Cleanup
            reset_search_backend()

    def test_health_endpoint(self):
        """Test that health endpoint works."""
        client = TestClient(app)
        response = client.get("/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_search_basic(self, client_with_backend):
        """Test basic search request."""
        response = client_with_backend.post(
            "/v1/search",
            json={
                "query": "test query",
                "top_k": 10,
                "embed_model": "small",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "hits" in data
        assert "meta" in data

        # Verify hits
        assert len(data["hits"]) == 2
        assert data["hits"][0]["chunk_id"] in ["chunk1", "chunk2"]

        # Verify metadata
        assert data["meta"]["top_k"] == 10
        assert data["meta"]["model"] == "small"
        assert "latency_ms" in data["meta"]
        assert isinstance(data["meta"]["latency_ms"], int)

    def test_search_with_top_k_limit(self, client_with_backend):
        """Test that top_k parameter limits results."""
        response = client_with_backend.post(
            "/v1/search",
            json={
                "query": "test query",
                "top_k": 1,
                "embed_model": "small",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should only return 1 result
        assert len(data["hits"]) == 1

    def test_search_with_repo_filter(self, client_with_backend):
        """Test search with repository filter."""
        response = client_with_backend.post(
            "/v1/search",
            json={
                "query": "test query",
                "repos": ["test-repo"],
                "embed_model": "small",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["hits"]) >= 1
        for hit in data["hits"]:
            assert hit["repo"] == "test-repo"

    def test_search_with_path_prefix(self, client_with_backend):
        """Test search with path prefix filter."""
        response = client_with_backend.post(
            "/v1/search",
            json={
                "query": "test query",
                "path_prefix": ["src/main.py"],
                "embed_model": "small",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should only return results from src/main.py
        assert len(data["hits"]) == 1
        assert data["hits"][0]["path"] == "src/main.py"

    def test_search_with_defaults(self, client_with_backend):
        """Test search with default parameters."""
        response = client_with_backend.post(
            "/v1/search",
            json={"query": "test query"},
        )

        assert response.status_code == 200
        data = response.json()

        # Should use defaults from SearchRequest
        assert data["meta"]["top_k"] == 8  # Default top_k
        assert data["meta"]["model"] == "small"  # Default embed_model

    def test_search_empty_query(self, client_with_backend):
        """Test search with empty query."""
        response = client_with_backend.post(
            "/v1/search",
            json={"query": ""},
        )

        # Should still work (returns results based on zero-vector for stub)
        assert response.status_code == 200

    def test_search_without_backend(self):
        """Test search returns empty results without backend configured."""
        reset_search_backend()
        client = TestClient(app)

        response = client.post(
            "/v1/search",
            json={"query": "test"},
        )

        assert response.status_code == 200
        data = response.json()

        # Empty backend returns no hits
        assert data["hits"] == []

    def test_search_invalid_request(self):
        """Test search with invalid request body."""
        client = TestClient(app)

        response = client.post(
            "/v1/search",
            json={},  # Missing required 'query' field
        )

        assert response.status_code == 422  # Validation error

    def test_search_response_timing(self, client_with_backend):
        """Test that latency is measured and reasonable."""
        response = client_with_backend.post(
            "/v1/search",
            json={"query": "test query"},
        )

        assert response.status_code == 200
        data = response.json()

        # Latency should be present and reasonable (< 1 second for stub provider)
        assert "latency_ms" in data["meta"]
        assert 0 <= data["meta"]["latency_ms"] < 1000

    def test_search_large_model(self, client_with_backend):
        """Test search with large embedding model."""
        # Note: This will fail because we only indexed with 'small' model
        # But it should still execute without errors
        response = client_with_backend.post(
            "/v1/search",
            json={
                "query": "test query",
                "embed_model": "large",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should return empty since we indexed with 'small' model
        assert len(data["hits"]) == 0
        assert data["meta"]["model"] == "large"
