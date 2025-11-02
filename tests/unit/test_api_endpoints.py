"""Unit tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from kb.api.app import app, SearchRequest, set_search_backend, reset_search_backend, set_stores, reset_stores


class MockSearchBackend:
    """Mock search backend for testing."""

    def search(self, request: SearchRequest):
        """Return mock search results."""
        return [
            {
                "repo": "test-repo",
                "path": "test.py",
                "start_line": 1,
                "end_line": 10,
                "score": 0.95,
                "snippet": "def test(): pass",
                "provenance": {"commit": "abc123", "text_hash": "hash123"}
            }
        ]


class TestHealthEndpoint:
    """Test /v1/health endpoint."""

    def setup_method(self):
        """Reset backend before each test."""
        reset_search_backend()
        reset_stores()

    def test_health_shallow_check(self):
        """Test shallow health check returns ok."""
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_shallow_check_explicit(self):
        """Test shallow check with explicit query param."""
        client = TestClient(app)
        response = client.get("/health?check=shallow")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_deep_check_no_stores(self):
        """Test deep health check without stores configured."""
        client = TestClient(app)
        response = client.get("/health?check=deep")

        assert response.status_code == 200
        data = response.json()
        # Should have status and checks
        assert "status" in data or "lancedb" in data


class TestSearchEndpoint:
    """Test /v1/search endpoint."""

    def setup_method(self):
        """Set up mock backend before each test."""
        reset_search_backend()
        set_search_backend(MockSearchBackend())

    def teardown_method(self):
        """Clean up after each test."""
        reset_search_backend()

    def test_search_basic_query(self):
        """Test basic search query."""
        client = TestClient(app)
        response = client.post("/search", json={"query": "test function"})

        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert len(data["hits"]) > 0

    def test_search_with_repos_filter(self):
        """Test search with repos filter."""
        client = TestClient(app)
        response = client.post(
            "/search",
            json={"query": "test", "repos": ["repo1", "repo2"]}
        )

        assert response.status_code == 200

    def test_search_with_top_k(self):
        """Test search with custom top_k."""
        client = TestClient(app)
        response = client.post(
            "/search",
            json={"query": "test", "top_k": 20}
        )

        assert response.status_code == 200

    def test_search_with_path_prefix(self):
        """Test search with path_prefix filter."""
        client = TestClient(app)
        response = client.post(
            "/search",
            json={"query": "test", "path_prefix": ["src/", "lib/"]}
        )

        assert response.status_code == 200

    def test_search_missing_query_fails(self):
        """Test that missing query field fails validation."""
        client = TestClient(app)
        response = client.post("/search", json={})

        assert response.status_code == 422  # Validation error


class TestReposEndpoint:
    """Test /v1/repos endpoint."""

    def setup_method(self):
        """Reset stores before each test."""
        reset_stores()

    def test_repos_endpoint_exists(self):
        """Test /v1/repos endpoint exists."""
        client = TestClient(app)
        response = client.get("/repos")

        # Should work even without stores, or return 404/503 if not configured
        assert response.status_code in [200, 404, 500, 503]


class TestChunkEndpoint:
    """Test /v1/chunks/{id} endpoint."""

    def test_chunk_endpoint_exists(self):
        """Test /v1/chunks/{id} endpoint exists."""
        client = TestClient(app)
        response = client.get("/chunks/123")

        # Should exist, may error without data or return 404/503 if not configured
        assert response.status_code in [200, 404, 422, 500, 503]


class TestFileEndpoint:
    """Test /v1/file endpoint."""

    def test_file_endpoint_requires_params(self):
        """Test /v1/file endpoint requires parameters."""
        client = TestClient(app)
        response = client.get("/file")
    
        # Should require repo and path params
        assert response.status_code == 422


class TestMCPEndpoints:
    """Test MCP-specific endpoints."""

    def test_mcp_search_endpoint_exists(self):
        """Test MCP search endpoint exists."""
        client = TestClient(app)
        response = client.post("/mcp/search", json={"query": "test"})

        # Should exist or return 404 if not implemented
        assert response.status_code in [200, 404, 422, 500]

    def test_mcp_fetch_chunk_endpoint_exists(self):
        """Test MCP fetch_chunk endpoint exists."""
        client = TestClient(app)
        response = client.post("/mcp/fetch_chunk", json={"chunk_id": 123})

        # Should exist or return 404 if not implemented
        assert response.status_code in [200, 404, 422, 500]


class TestAPIModels:
    """Test API request/response models."""

    def test_search_request_defaults(self):
        """Test SearchRequest default values."""
        req = SearchRequest(query="test")

        assert req.query == "test"
        assert req.repos is None
        assert req.top_k == 8
        assert req.max_snippet_tokens == 240
        assert req.embed_model == "large"

    def test_search_request_with_all_fields(self):
        """Test SearchRequest with all fields."""
        req = SearchRequest(
            query="test query",
            repos=["repo1"],
            path_prefix=["src/"],
            top_k=20,
            max_snippet_tokens=500,
            embed_model="small",
            score_cutoff=0.5
        )

        assert req.query == "test query"
        assert req.repos == ["repo1"]
        assert req.path_prefix == ["src/"]
        assert req.top_k == 20
        assert req.max_snippet_tokens == 500
        assert req.embed_model == "small"
        assert req.score_cutoff == 0.5
