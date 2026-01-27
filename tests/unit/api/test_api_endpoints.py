"""Unit tests for FastAPI endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb.api.app import SearchRequest, app, reset_search_backend, reset_stores, set_search_backend, set_stores
from kb.api_key import get_kb_key_path


class MockSearchBackend:
    """Mock search backend for testing."""

    def search(self, request: SearchRequest):
        """Return mock search results."""
        return (
            [
                {
                    "repo": "test-repo",
                    "path": "test.py",
                    "start_line": 1,
                    "end_line": 10,
                    "score": 0.95,
                    "snippet": "def test(): pass",
                    "provenance": {"commit": "abc123", "text_hash": "hash123"},
                }
            ],
            None,
        )


class TestHealthEndpoint:
    """Test /v1/health endpoint."""

    def setup_method(self):
        """Reset backend before each test."""
        reset_search_backend()
        reset_stores()

    def test_health_shallow_check(self):
        """Test shallow health check returns ok."""
        client = TestClient(app)
        response = client.get("/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_shallow_check_explicit(self):
        """Test shallow check with explicit query param."""
        client = TestClient(app)
        response = client.get("/v1/health?check=shallow")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_deep_check_no_stores(self):
        """Test deep health check without stores configured."""
        client = TestClient(app)
        response = client.get("/v1/health?check=deep")

        assert response.status_code == 200
        data = response.json()
        # Should have status and checks
        assert "status" in data or "lancedb" in data

    def test_health_v1_shallow_check(self, kb_api_client):
        """Test /v1/health with API key."""
        response = kb_api_client.get("/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSearchEndpoint:
    """Test /v1/search endpoint."""

    def setup_method(self):
        """Set up mock backend before each test."""
        reset_search_backend()
        set_search_backend(MockSearchBackend())

    def teardown_method(self):
        """Clean up after each test."""
        reset_search_backend()

    def test_search_requires_api_key(self):
        """All /v1 endpoints (except /v1/health) require an API key."""
        client = TestClient(app)
        response = client.post("/v1/search", json={"query": "test function"})
        assert response.status_code == 401

    def test_search_v1_basic_query(self, kb_api_client):
        """Test /v1/search with API key."""
        response = kb_api_client.post("/v1/search", json={"query": "test function"})

        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert len(data["hits"]) > 0
        assert data["meta"]["max_snippets"] == 0

    def test_search_v1_unknown_repo_returns_404(self, kb_api_client):
        """Unknown repos should return a 404 with a helpful message."""
        response = kb_api_client.post(
            "/v1/search",
            json={"query": "test", "repos": ["does-not-exist"]},
        )

        assert response.status_code == 404
        assert "Repository not found" in response.json().get("detail", "")

    def test_search_with_repos_filter(self, kb_api_client, registered_test_repo):
        """Test search with repos filter."""
        response = kb_api_client.post(
            "/v1/search",
            json={"query": "test", "repos": [registered_test_repo["name"]]},
        )

        assert response.status_code == 200

    def test_search_with_top_k(self, kb_api_client):
        """Test search with custom top_k."""
        response = kb_api_client.post("/v1/search", json={"query": "test", "top_k": 20})

        assert response.status_code == 200

    def test_search_with_path_prefix(self, kb_api_client):
        """Test search with path_prefix filter."""
        response = kb_api_client.post("/v1/search", json={"query": "test", "path_prefix": ["src/", "lib/"]})

        assert response.status_code == 200

    def test_search_missing_query_fails(self, kb_api_client):
        """Test that missing query field fails validation."""
        response = kb_api_client.post("/v1/search", json={})

        assert response.status_code == 422  # Validation error

    def test_search_v1_snippets_with_context(self, mock_kb_stores, tmp_path, monkeypatch):
        """Test v1 search snippet enrichment with context lines."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        file_path = repo_root / "test.py"
        file_path.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")

        sql_store.record_repo(name="test-repo", path=repo_root, default_embed_model="large")

        class BackendNoSnippet:
            def search(self, request: SearchRequest):
                return (
                    [
                        {
                            "repo": "test-repo",
                            "path": "test.py",
                            "start_line": 2,
                            "end_line": 3,
                            "score": 0.9,
                            "chunk_id": "c1",
                        }
                    ],
                    None,
                )

        set_search_backend(BackendNoSnippet())

        test_key = "test-api-key-12345"
        monkeypatch.setenv("DOLPHIN_API_KEY", test_key)
        client = TestClient(app)
        client.headers = {"X-API-Key": test_key}

        response = client.post(
            "/v1/search",
            json={
                "query": "test",
                "max_snippets": 1,
                "context_lines_before": 1,
                "context_lines_after": 1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        hit = data["hits"][0]
        snippet = hit["snippet"]
        assert isinstance(snippet, dict)
        assert snippet["text"] == "line2\nline3\n"
        assert snippet["context_before"] == "line1\n"
        assert snippet["context_after"] == "line4\n"
        assert snippet["start_line"] == 1
        assert snippet["end_line"] == 4

        assert "snippet_start_line" not in hit
        assert "snippet_end_line" not in hit

        reset_search_backend()
        reset_stores()

        reset_search_backend()
        reset_stores()


class TestReposEndpoint:
    """Test /v1/repos endpoint."""

    def setup_method(self):
        """Reset stores before each test."""
        reset_stores()

    def test_repos_endpoint_exists(self, kb_api_client):
        """Test /v1/repos endpoint exists."""
        response = kb_api_client.get("/v1/repos")

        # Should work even without stores, or return 404/503 if not configured
        assert response.status_code in [200, 404, 500, 503]


class TestChunkEndpoint:
    """Test /v1/chunks/{id} endpoint."""

    def test_chunk_endpoint_exists(self, kb_api_client):
        """Test /v1/chunks/{id} endpoint exists."""
        response = kb_api_client.get("/v1/chunks/123")

        # Should exist, may error without data or return 404/503 if not configured
        assert response.status_code in [200, 404, 422, 500, 503]


class TestFileEndpoint:
    """Test /v1/file endpoint."""

    def test_file_endpoint_requires_params(self, kb_api_client):
        """Test /v1/file endpoint requires parameters."""
        response = kb_api_client.get("/v1/file")

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


class TestApiKeyMiddleware:
    """Tests for API key authentication on /v1 endpoints."""

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch):
        """Ensure env keys are cleared before each test."""
        for name in ("DOLPHIN_API_KEY", "DOLPHIN_KB_API_KEY"):
            monkeypatch.delenv(name, raising=False)

    def test_rejects_missing_key(self, monkeypatch):
        """Requests without a key should be unauthorized."""
        monkeypatch.setenv("DOLPHIN_API_KEY", "primary-key")

        client = TestClient(app)
        response = client.get("/v1/index/tasks")

        assert response.status_code == 401

    def test_accepts_primary_env_key(self, monkeypatch):
        """Primary env var should be accepted."""
        monkeypatch.setenv("DOLPHIN_API_KEY", "primary-key")

        client = TestClient(app)
        response = client.get("/v1/index/tasks", headers={"X-API-Key": "primary-key"})

        assert response.status_code == 200

    def test_accepts_legacy_env_key(self, monkeypatch):
        """Legacy env var should still be accepted."""
        monkeypatch.setenv("DOLPHIN_KB_API_KEY", "legacy-key")

        client = TestClient(app)
        response = client.get("/v1/index/tasks", headers={"X-API-Key": "legacy-key"})

        assert response.status_code == 200

    def test_falls_back_to_managed_key_file(self, monkeypatch, tmp_path: Path):
        """If no env vars are set, use the managed key file."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))

        key_path = get_kb_key_path()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text("file-key\n", encoding="utf-8")

        client = TestClient(app)
        response = client.get("/v1/index/tasks", headers={"X-API-Key": "file-key"})

        assert response.status_code == 200

    def test_search_request_defaults(self):
        """Test SearchRequest default values."""
        req = SearchRequest(query="test")

        assert req.query == "test"
        assert req.repos is None
        assert req.top_k == 8
        # embed_model removed - now uses global config
        assert req.max_snippets == 0

    def test_search_request_with_all_fields(self):
        """Test SearchRequest with all fields."""
        req = SearchRequest(
            query="test query",
            repos=["repo1"],
            path_prefix=["src/"],
            top_k=20,
            max_snippet_tokens=500,
            score_cutoff=0.5,
        )

        assert req.query == "test query"
        assert req.repos == ["repo1"]
        assert req.path_prefix == ["src/"]
        assert req.top_k == 20
        assert req.max_snippet_tokens == 500
        # embed_model removed - now uses global config
        assert req.score_cutoff == 0.5


class TestRegisterRepoEndpoint:
    """Test POST /v1/repos endpoint for repository registration."""

    def test_register_repo_success(self, kb_api_client, temp_dir):
        """Test successful repository registration."""
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        response = kb_api_client.post(
            "/v1/repos",
            json={
                "name": "test-repo",
                "path": str(workspace),
                "default_embed_model": "large",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-repo"
        # Normalize paths for comparison (macOS /var -> /private/var)
        assert Path(data["path"]).resolve() == workspace.resolve()
        assert "repo_id" in data

    def test_register_repo_missing_name(self, kb_api_client, temp_dir):
        """Test registration fails without name."""
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        response = kb_api_client.post("/v1/repos", json={"path": str(workspace), "default_embed_model": "large"})

        assert response.status_code == 422  # Validation error

    def test_register_repo_missing_path(self, kb_api_client):
        """Test registration fails without path."""
        response = kb_api_client.post("/v1/repos", json={"name": "test-repo", "default_embed_model": "large"})

        assert response.status_code == 422  # Validation error

    def test_register_repo_default_embed_model(self, kb_api_client, temp_dir):
        """Test registration with default embed model."""
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        response = kb_api_client.post("/v1/repos", json={"name": "test-repo", "path": str(workspace)})

        assert response.status_code == 200
        data = response.json()
        # Should use default model if not specified
        assert "repo_id" in data

    def test_register_repo_already_exists(self, kb_api_client, registered_test_repo):
        """Test registering same repo twice."""
        # First registration done by fixture
        # Try to register again
        response = kb_api_client.post(
            "/v1/repos",
            json={
                "name": registered_test_repo["name"],
                "path": registered_test_repo["path"],
                "default_embed_model": "large",
            },
        )

        # Should either succeed (idempotent) or return error
        assert response.status_code in [200, 400, 409]


class TestIndexEndpoint:
    """Test POST /v1/index endpoint for queueing file indexing."""

    def test_index_files_success(self, kb_api_client, registered_test_repo, mock_pipeline):
        """Test successfully queueing files for indexing."""
        from kb.api.app import set_pipeline

        set_pipeline(mock_pipeline)

        # Create test files
        workspace = registered_test_repo["workspace"]
        (workspace / "file1.py").write_text("def hello(): pass")
        (workspace / "file2.py").write_text("def world(): pass")

        response = kb_api_client.post(
            "/v1/index",
            json={
                "repo": registered_test_repo["name"],
                "files": ["file1.py", "file2.py"],
                "incremental": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "queued"
        assert "message" in data

    def test_index_files_nonexistent_repo(self, kb_api_client):
        """Test indexing files for non-existent repository."""
        response = kb_api_client.post("/v1/index", json={"repo": "nonexistent-repo", "files": ["file.py"]})

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_index_files_empty_list(self, kb_api_client, registered_test_repo):
        """Test indexing with empty file list."""
        response = kb_api_client.post("/v1/index", json={"repo": registered_test_repo["name"], "files": []})

        # Should still create task
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_index_files_missing_repo_param(self, kb_api_client):
        """Test indexing without repo parameter."""
        response = kb_api_client.post("/v1/index", json={"files": ["file.py"]})

        assert response.status_code == 422  # Validation error

    def test_index_files_missing_files_param(self, kb_api_client, registered_test_repo):
        """Test indexing without files parameter."""
        response = kb_api_client.post("/v1/index", json={"repo": registered_test_repo["name"]})

        assert response.status_code == 422  # Validation error

    def test_index_files_incremental_flag(self, kb_api_client, registered_test_repo, mock_pipeline):
        """Test incremental flag is passed correctly."""
        from kb.api.app import set_pipeline

        set_pipeline(mock_pipeline)

        workspace = registered_test_repo["workspace"]
        (workspace / "file.py").write_text("def test(): pass")

        response = kb_api_client.post(
            "/v1/index",
            json={
                "repo": registered_test_repo["name"],
                "files": ["file.py"],
                "incremental": False,
            },
        )

        assert response.status_code == 200


class TestIndexStatusEndpoint:
    """Test GET /v1/index/status/{task_id} endpoint."""

    def test_get_task_status_queued(self, kb_api_client, registered_test_repo, mock_pipeline):
        """Test getting status of queued task."""
        from kb.api.app import set_pipeline

        set_pipeline(mock_pipeline)

        # Queue a task
        queue_response = kb_api_client.post(
            "/v1/index",
            json={"repo": registered_test_repo["name"], "files": ["file.py"]},
        )
        task_id = queue_response.json()["task_id"]

        # Get status
        response = kb_api_client.get(f"/v1/index/status/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] in ["queued", "processing", "completed"]
        assert "progress" in data
        assert "total" in data

    def test_get_task_status_nonexistent(self, kb_api_client):
        """Test getting status of non-existent task."""
        response = kb_api_client.get("/v1/index/status/nonexistent-task-id")

        assert response.status_code == 404

    def test_get_task_status_structure(self, kb_api_client, registered_test_repo, mock_pipeline):
        """Test status response structure."""
        from kb.api.app import set_pipeline

        set_pipeline(mock_pipeline)

        # Queue a task
        queue_response = kb_api_client.post(
            "/v1/index",
            json={
                "repo": registered_test_repo["name"],
                "files": ["a.py", "b.py", "c.py"],
            },
        )
        task_id = queue_response.json()["task_id"]

        # Get status
        response = kb_api_client.get(f"/v1/index/status/{task_id}")

        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert "task_id" in data
        assert "status" in data
        assert "progress" in data
        assert "total" in data
        assert data["total"] == 3


class TestIndexTasksEndpoint:
    """Test GET /v1/index/tasks endpoint."""

    def test_list_tasks_empty(self, kb_api_client):
        """Test listing tasks when none exist."""
        response = kb_api_client.get("/v1/index/tasks")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    def test_list_tasks_with_tasks(self, kb_api_client, registered_test_repo, mock_pipeline):
        """Test listing tasks."""
        from kb.api.app import set_pipeline

        set_pipeline(mock_pipeline)

        # Queue multiple tasks
        kb_api_client.post("/v1/index", json={"repo": registered_test_repo["name"], "files": ["a.py"]})
        kb_api_client.post("/v1/index", json={"repo": registered_test_repo["name"], "files": ["b.py"]})

        # List tasks
        response = kb_api_client.get("/v1/index/tasks")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) >= 2

    def test_list_tasks_filtered_by_repo(self, kb_api_client, mock_kb_stores, mock_pipeline, temp_dir):
        """Test listing tasks filtered by repository."""
        from kb.api.app import set_pipeline

        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        set_pipeline(mock_pipeline)

        # Create two repos
        workspace1 = temp_dir / "workspace1"
        workspace1.mkdir()
        workspace2 = temp_dir / "workspace2"
        workspace2.mkdir()

        sql_store.record_repo(name="repo1", path=workspace1, default_embed_model="large")
        sql_store.record_repo(name="repo2", path=workspace2, default_embed_model="large")

        # Queue tasks for each repo
        kb_api_client.post("/v1/index", json={"repo": "repo1", "files": ["a.py"]})
        kb_api_client.post("/v1/index", json={"repo": "repo2", "files": ["b.py"]})
        kb_api_client.post("/v1/index", json={"repo": "repo1", "files": ["c.py"]})

        # Filter by repo1
        response = kb_api_client.get("/v1/index/tasks?repo=repo1")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        # All tasks should be for repo1
        for task in data["tasks"]:
            assert task["repo"] == "repo1"

    def test_list_tasks_response_structure(self, kb_api_client, registered_test_repo, mock_pipeline):
        """Test task list response structure."""
        from kb.api.app import set_pipeline

        set_pipeline(mock_pipeline)

        # Queue a task
        kb_api_client.post(
            "/v1/index",
            json={"repo": registered_test_repo["name"], "files": ["file.py"]},
        )

        # List tasks
        response = kb_api_client.get("/v1/index/tasks")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data

        if len(data["tasks"]) > 0:
            task = data["tasks"][0]
            # Verify task structure
            assert "task_id" in task
            assert "repo" in task
            assert "status" in task
            assert "progress" in task
            assert "total" in task
