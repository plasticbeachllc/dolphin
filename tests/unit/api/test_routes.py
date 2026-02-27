"""Unit tests for API route modules in kb/api/routes/."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from kb.api.app import (
    SearchRequest,
    app,
    reset_search_backend,
    reset_stores,
    set_pipeline,
    set_search_backend,
    set_stores,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockSearchBackend:
    """Minimal mock search backend returning canned results."""

    def __init__(self, results=None, error=None):
        self._results = results or []
        self._error = error

    def search(self, request: SearchRequest):
        if self._error:
            raise self._error
        return (self._results, None)

    def close(self):
        pass


def _make_api_client(monkeypatch, api_key: str = "test-key-routes"):
    """Return a TestClient with the given API key configured."""
    monkeypatch.setenv("DOLPHIN_API_KEY", api_key)
    client = TestClient(app)
    client.headers = {"X-API-Key": api_key}
    return client


# ===================================================================
# Health Routes
# ===================================================================


class TestHealthRoutes:
    """Tests for /v1/health endpoint (kb/api/routes/health.py)."""

    def setup_method(self):
        reset_search_backend()
        reset_stores()

    def test_shallow_health_default(self):
        """GET /v1/health returns status ok by default (shallow)."""
        client = TestClient(app)
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_shallow_health_explicit_param(self):
        """GET /v1/health?check=shallow returns status ok."""
        client = TestClient(app)
        resp = client.get("/v1/health?check=shallow")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_deep_health_without_stores(self):
        """Deep check succeeds even when stores are None."""
        client = TestClient(app)
        resp = client.get("/v1/health?check=deep")
        assert resp.status_code == 200
        data = resp.json()
        # Deep check includes subsystem keys
        assert "lancedb" in data or "status" in data

    def test_health_does_not_require_api_key(self):
        """Health endpoint is exempt from API key middleware."""
        client = TestClient(app)
        resp = client.get("/v1/health")
        assert resp.status_code == 200


# ===================================================================
# Search Routes
# ===================================================================


class TestSearchRoutes:
    """Tests for /v1/search endpoint (kb/api/routes/search.py)."""

    def setup_method(self):
        reset_search_backend()
        reset_stores()

    def teardown_method(self):
        reset_search_backend()
        reset_stores()

    def test_search_requires_api_key(self):
        """POST /v1/search without API key returns 401."""
        client = TestClient(app)
        resp = client.post("/v1/search", json={"query": "hello"})
        assert resp.status_code == 401

    def test_search_invalid_api_key(self, monkeypatch):
        """POST /v1/search with wrong API key returns 401."""
        monkeypatch.setenv("DOLPHIN_API_KEY", "correct-key")
        client = TestClient(app)
        client.headers = {"X-API-Key": "wrong-key"}
        resp = client.post("/v1/search", json={"query": "hello"})
        assert resp.status_code == 401

    def test_search_missing_query_returns_422(self, monkeypatch):
        """POST /v1/search without query field returns 422."""
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/search", json={})
        assert resp.status_code == 422

    def test_search_basic_query(self, monkeypatch):
        """POST /v1/search returns hits from backend."""
        hit = {
            "repo": "r",
            "path": "a.py",
            "start_line": 1,
            "end_line": 5,
            "score": 0.9,
            "snippet": "code",
        }
        set_search_backend(_MockSearchBackend(results=[hit]))
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/search", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "hits" in data
        assert len(data["hits"]) >= 1

    def test_search_with_top_k(self, monkeypatch):
        """Custom top_k is accepted."""
        set_search_backend(_MockSearchBackend())
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/search", json={"query": "test", "top_k": 3})
        assert resp.status_code == 200

    def test_search_with_path_prefix(self, monkeypatch):
        """path_prefix filter is accepted."""
        set_search_backend(_MockSearchBackend())
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/search", json={"query": "test", "path_prefix": ["src/"]})
        assert resp.status_code == 200

    def test_search_unknown_repo_returns_404(self, monkeypatch, mock_kb_stores):
        """Searching in a non-existent repo returns 404."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        set_search_backend(_MockSearchBackend())
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/search", json={"query": "test", "repos": ["no-such-repo"]})
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()


# ===================================================================
# File / Chunk Routes
# ===================================================================


class TestFileRoutes:
    """Tests for /v1/file and /v1/chunks endpoints (kb/api/routes/files.py)."""

    def setup_method(self):
        reset_search_backend()
        reset_stores()

    def teardown_method(self):
        reset_stores()

    def test_file_endpoint_requires_params(self, monkeypatch):
        """GET /v1/file without required params returns 422."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/file")
        assert resp.status_code == 422

    def test_file_endpoint_invalid_line_range(self, monkeypatch):
        """GET /v1/file with start > end returns 422."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/file?repo=r&path=a.py&start=10&end=5")
        assert resp.status_code == 422

    def test_file_endpoint_start_less_than_one(self, monkeypatch):
        """GET /v1/file with start < 1 returns 422."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/file?repo=r&path=a.py&start=0&end=5")
        assert resp.status_code == 422

    def test_file_slice_stores_not_initialized(self, monkeypatch):
        """GET /v1/file returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/file?repo=r&path=a.py&start=1&end=5")
        assert resp.status_code == 503

    def test_file_slice_repo_not_found(self, monkeypatch, mock_kb_stores):
        """GET /v1/file returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/file?repo=no-repo&path=a.py&start=1&end=5")
        assert resp.status_code == 404

    def test_file_slice_success(self, monkeypatch, mock_kb_stores, tmp_path):
        """GET /v1/file returns file content for valid request."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)

        workspace = tmp_path / "ws"
        workspace.mkdir()
        target = workspace / "hello.py"
        target.write_text("line1\nline2\nline3\n", encoding="utf-8")
        sql_store.record_repo(name="test-repo", path=workspace, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/file?repo=test-repo&path=hello.py&start=1&end=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data or "lines" in data or "text" in data

    def test_chunk_not_found(self, monkeypatch, mock_kb_stores):
        """GET /v1/chunks/{id} returns 404 for missing chunk."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        lance_store.get_chunk_by_id.return_value = None
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/chunks/abc123")
        assert resp.status_code == 404

    def test_chunk_invalid_id_format(self, monkeypatch, mock_kb_stores):
        """GET /v1/chunks/{id} rejects invalid chunk_id format."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        # chunk_id with special characters that fail the CHUNK_ID_PATTERN regex
        resp = client.get("/v1/chunks/bad%20id!@%23")
        assert resp.status_code == 400

    def test_chunk_stores_not_initialized(self, monkeypatch):
        """GET /v1/chunks/{id} returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/chunks/abc123")
        assert resp.status_code == 503


# ===================================================================
# Repos Routes
# ===================================================================


class TestReposRoutes:
    """Tests for /v1/repos endpoints (kb/api/routes/repos.py)."""

    def setup_method(self):
        reset_search_backend()
        reset_stores()

    def teardown_method(self):
        reset_stores()

    # ---- list repos ----

    def test_list_repos_stores_not_initialized(self, monkeypatch):
        """GET /v1/repos returns 503 when SQL store is None."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos")
        assert resp.status_code == 503

    def test_list_repos_empty(self, monkeypatch, mock_kb_stores):
        """GET /v1/repos returns empty list when no repos registered."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert "repos" in data
        assert isinstance(data["repos"], list)

    def test_list_repos_after_registration(self, monkeypatch, mock_kb_stores, tmp_path):
        """GET /v1/repos returns registered repos."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="my-repo", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos")
        assert resp.status_code == 200
        data = resp.json()
        names = [r.get("name") for r in data["repos"]]
        assert "my-repo" in names

    # ---- register repo ----

    def test_register_repo_success(self, monkeypatch, mock_kb_stores, tmp_path):
        """POST /v1/repos registers a new repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "workspace"
        ws.mkdir()

        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos",
            json={"name": "new-repo", "path": str(ws), "default_embed_model": "large"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new-repo"
        assert "repo_id" in data

    def test_register_repo_already_exists(self, monkeypatch, mock_kb_stores, tmp_path):
        """POST /v1/repos for existing name returns idempotent response."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "workspace"
        ws.mkdir()
        sql_store.record_repo(name="existing", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos",
            json={"name": "existing", "path": str(ws), "default_embed_model": "large"},
        )
        assert resp.status_code == 200
        assert "already registered" in resp.json().get("message", "").lower()

    def test_register_repo_missing_name(self, monkeypatch, mock_kb_stores, tmp_path):
        """POST /v1/repos without name returns 422."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "workspace"
        ws.mkdir()
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/repos", json={"path": str(ws)})
        assert resp.status_code == 422

    def test_register_repo_missing_path(self, monkeypatch, mock_kb_stores):
        """POST /v1/repos without path returns 422."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/repos", json={"name": "repo"})
        assert resp.status_code == 422

    def test_register_repo_sql_store_none(self, monkeypatch):
        """POST /v1/repos returns 503 when SQL store is None."""
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/repos", json={"name": "r", "path": "/tmp/x"})
        assert resp.status_code == 503

    # ---- repo stats ----

    def test_repo_stats_not_found(self, monkeypatch, mock_kb_stores):
        """GET /v1/repos/{name}/stats returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/no-repo/stats")
        assert resp.status_code == 404

    def test_repo_stats_stores_not_initialized(self, monkeypatch):
        """GET /v1/repos/{name}/stats returns 503 when SQL store is None."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/some-repo/stats")
        assert resp.status_code == 503

    def test_repo_stats_success(self, monkeypatch, mock_kb_stores, tmp_path):
        """GET /v1/repos/{name}/stats returns expected fields."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="stats-repo", path=ws, default_embed_model="large")

        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/stats-repo/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "stats-repo"
        assert "files_count" in data
        assert "chunks_count" in data
        assert "total_tokens" in data
        assert "embed_model" in data
        assert "needs_reindex" in data

    # ---- reindex ----

    def test_reindex_repo_not_found(self, monkeypatch, mock_kb_stores):
        """POST /v1/repos/{name}/reindex returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/ghost/reindex",
            json={"mode": "full", "confirmed": True},
        )
        assert resp.status_code == 404

    def test_reindex_stores_not_initialized(self, monkeypatch):
        """POST /v1/repos/{name}/reindex returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/repo/reindex",
            json={"mode": "full", "confirmed": True},
        )
        assert resp.status_code == 503

    def test_reindex_full_requires_confirmation(self, monkeypatch, mock_kb_stores, tmp_path):
        """Full reindex without confirmation returns 400."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="rr", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/rr/reindex",
            json={"mode": "full", "confirmed": False},
        )
        assert resp.status_code == 400
        assert "confirmation" in resp.json()["detail"].lower()

    def test_reindex_invalid_mode(self, monkeypatch, mock_kb_stores, tmp_path):
        """Reindex with invalid mode returns 400."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="rr", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/rr/reindex",
            json={"mode": "bogus", "confirmed": True},
        )
        assert resp.status_code == 400

    @patch("kb.ingest._helpers.get_all_tracked_files", return_value=["a.py", "b.py"])
    def test_reindex_full_confirmed_queues_task(self, mock_files, monkeypatch, mock_kb_stores, tmp_path):
        """Full confirmed reindex queues a background task."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="rr", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/rr/reindex",
            json={"mode": "full", "confirmed": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert "task_id" in data

    # ---- clear index ----

    def test_clear_index_requires_confirmation(self, monkeypatch, mock_kb_stores, tmp_path):
        """DELETE /v1/repos/{name}/index without confirmed returns 400."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="cr", path=ws, default_embed_model="small")

        pipeline = MagicMock()
        set_pipeline(pipeline)

        client = _make_api_client(monkeypatch)
        resp = client.delete("/v1/repos/cr/index")
        assert resp.status_code == 400

    def test_clear_index_repo_not_found(self, monkeypatch, mock_kb_stores):
        """DELETE /v1/repos/{name}/index returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        pipeline = MagicMock()
        set_pipeline(pipeline)

        client = _make_api_client(monkeypatch)
        resp = client.delete("/v1/repos/ghost/index?confirmed=true")
        assert resp.status_code == 404

    def test_clear_index_stores_not_initialized(self, monkeypatch):
        """DELETE /v1/repos/{name}/index returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.delete("/v1/repos/r/index?confirmed=true")
        assert resp.status_code == 503

    def test_clear_index_success(self, monkeypatch, mock_kb_stores, tmp_path):
        """DELETE /v1/repos/{name}/index succeeds when confirmed."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="cr", path=ws, default_embed_model="small")

        pipeline = MagicMock()
        set_pipeline(pipeline)

        client = _make_api_client(monkeypatch)
        resp = client.delete("/v1/repos/cr/index?confirmed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        pipeline._drop_repo_index.assert_called_once()

    # ---- pending changes ----

    def test_record_pending_changes_repo_not_found(self, monkeypatch, mock_kb_stores):
        """POST /v1/repos/{name}/changes returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/ghost/changes",
            json={"changes": [{"file_path": "a.py", "change_type": "modified"}]},
        )
        assert resp.status_code == 404

    def test_record_pending_changes_success(self, monkeypatch, mock_kb_stores, tmp_path):
        """POST /v1/repos/{name}/changes records changes."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="pc", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/pc/changes",
            json={"changes": [{"file_path": "a.py", "change_type": "modified"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "change_ids" in data
        assert len(data["change_ids"]) == 1

    def test_record_pending_changes_stores_none(self, monkeypatch):
        """POST /v1/repos/{name}/changes returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/r/changes",
            json={"changes": [{"file_path": "a.py", "change_type": "modified"}]},
        )
        assert resp.status_code == 503

    # ---- get pending changes ----

    def test_get_pending_changes_repo_not_found(self, monkeypatch, mock_kb_stores):
        """GET /v1/repos/{name}/pending-changes returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/ghost/pending-changes")
        assert resp.status_code == 404

    def test_get_pending_changes_empty(self, monkeypatch, mock_kb_stores, tmp_path):
        """GET /v1/repos/{name}/pending-changes returns empty when none exist."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="pc", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/pc/pending-changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["changes"] == []

    def test_get_pending_changes_stores_none(self, monkeypatch):
        """GET /v1/repos/{name}/pending-changes returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/r/pending-changes")
        assert resp.status_code == 503

    # ---- mark processed ----

    def test_mark_processed_repo_not_found(self, monkeypatch, mock_kb_stores):
        """POST /v1/repos/{name}/changes/mark-processed returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/ghost/changes/mark-processed",
            json={"change_ids": [1, 2]},
        )
        assert resp.status_code == 404

    def test_mark_processed_stores_none(self, monkeypatch):
        """POST /v1/repos/{name}/changes/mark-processed returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.post(
            "/v1/repos/r/changes/mark-processed",
            json={"change_ids": [1]},
        )
        assert resp.status_code == 503

    # ---- drift detection ----

    def test_drift_repo_not_found(self, monkeypatch, mock_kb_stores):
        """GET /v1/repos/{name}/drift returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/ghost/drift")
        assert resp.status_code == 404

    def test_drift_stores_none(self, monkeypatch):
        """GET /v1/repos/{name}/drift returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/r/drift")
        assert resp.status_code == 503

    def test_drift_success(self, monkeypatch, mock_kb_stores, tmp_path):
        """GET /v1/repos/{name}/drift returns drift events."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="dr", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/repos/dr/drift")
        assert resp.status_code == 200
        data = resp.json()
        assert "drift_events" in data
        assert "total" in data


# ===================================================================
# Tasks Routes
# ===================================================================


class TestTasksRoutes:
    """Tests for /v1/index and /v1/admin endpoints (kb/api/routes/tasks.py)."""

    def setup_method(self):
        reset_search_backend()
        reset_stores()

    def teardown_method(self):
        reset_stores()

    # ---- index files ----

    def test_index_files_stores_not_initialized(self, monkeypatch):
        """POST /v1/index returns 503 when stores are None."""
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/index", json={"repo": "r", "files": ["a.py"]})
        assert resp.status_code == 503

    def test_index_files_repo_not_found(self, monkeypatch, mock_kb_stores):
        """POST /v1/index returns 404 for unknown repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/index", json={"repo": "ghost", "files": ["a.py"]})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_index_files_missing_repo(self, monkeypatch):
        """POST /v1/index without repo returns 422."""
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/index", json={"files": ["a.py"]})
        assert resp.status_code == 422

    def test_index_files_missing_files(self, monkeypatch, mock_kb_stores, tmp_path):
        """POST /v1/index without files returns 422."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="ir", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/index", json={"repo": "ir"})
        assert resp.status_code == 422

    def test_index_files_success(self, monkeypatch, mock_kb_stores, tmp_path):
        """POST /v1/index queues indexing task and returns task_id."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="ir", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/index", json={"repo": "ir", "files": ["a.py", "b.py"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "queued"

    # ---- index status ----

    def test_index_status_not_found(self, monkeypatch):
        """GET /v1/index/status/{id} returns 404 for unknown task."""
        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/index/status/does-not-exist")
        assert resp.status_code == 404

    def test_index_status_after_queue(self, monkeypatch, mock_kb_stores, tmp_path):
        """GET /v1/index/status/{id} returns queued status after indexing."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="ir", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        queue_resp = client.post("/v1/index", json={"repo": "ir", "files": ["a.py"]})
        task_id = queue_resp.json()["task_id"]

        resp = client.get(f"/v1/index/status/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("queued", "processing", "completed")
        assert "progress" in data
        assert "total" in data

    # ---- list tasks ----

    def test_list_tasks_empty(self, monkeypatch):
        """GET /v1/index/tasks returns empty list when no tasks exist."""
        # Reset the global task queue to guarantee empty state
        import kb.api.task_queue as tq_mod

        tq_mod._task_queue = None

        client = _make_api_client(monkeypatch)
        resp = client.get("/v1/index/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    def test_list_tasks_filtered_by_repo(self, monkeypatch, mock_kb_stores, tmp_path):
        """GET /v1/index/tasks?repo=X returns only tasks for that repo."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)

        ws1 = tmp_path / "ws1"
        ws1.mkdir()
        ws2 = tmp_path / "ws2"
        ws2.mkdir()
        sql_store.record_repo(name="alpha", path=ws1, default_embed_model="small")
        sql_store.record_repo(name="beta", path=ws2, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        client.post("/v1/index", json={"repo": "alpha", "files": ["a.py"]})
        client.post("/v1/index", json={"repo": "beta", "files": ["b.py"]})

        resp = client.get("/v1/index/tasks?repo=alpha")
        assert resp.status_code == 200
        for task in resp.json()["tasks"]:
            assert task["repo"] == "alpha"

    def test_list_tasks_response_structure(self, monkeypatch, mock_kb_stores, tmp_path):
        """Task objects contain expected fields."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        ws = tmp_path / "ws"
        ws.mkdir()
        sql_store.record_repo(name="sr", path=ws, default_embed_model="small")

        client = _make_api_client(monkeypatch)
        client.post("/v1/index", json={"repo": "sr", "files": ["f.py"]})

        resp = client.get("/v1/index/tasks")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert len(tasks) >= 1
        t = tasks[0]
        for key in ("task_id", "repo", "status", "progress", "total", "created_at"):
            assert key in t, f"Missing key: {key}"

    # ---- admin reload ----

    def test_admin_reload_success(self, monkeypatch):
        """POST /v1/admin/reload returns ok when reload succeeds."""
        import sys
        import types

        # Create a fake server module with a no-op reload_search_backend
        fake_server = types.ModuleType("kb.api.server")
        fake_server.reload_search_backend = lambda: None  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "kb.api.server", fake_server)

        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/admin/reload")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_admin_reload_failure_returns_500(self, monkeypatch):
        """POST /v1/admin/reload returns 500 when reload raises."""
        import sys
        import types

        fake_server = types.ModuleType("kb.api.server")

        def _boom():
            raise RuntimeError("reload exploded")

        fake_server.reload_search_backend = _boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "kb.api.server", fake_server)

        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/admin/reload")
        assert resp.status_code == 500

    # ---- admin rebuild FTS5 ----

    def test_rebuild_fts5_stores_not_initialized(self, monkeypatch):
        """POST /v1/admin/rebuild-fts5 returns 503 when SQL store is None."""
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/admin/rebuild-fts5")
        assert resp.status_code == 503

    def test_rebuild_fts5_success(self, monkeypatch, mock_kb_stores):
        """POST /v1/admin/rebuild-fts5 returns success message."""
        sql_store, lance_store = mock_kb_stores
        set_stores(sql_store, lance_store)
        client = _make_api_client(monkeypatch)
        resp = client.post("/v1/admin/rebuild-fts5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"


# ===================================================================
# Auth Middleware (across all protected routes)
# ===================================================================


class TestAuthMiddleware:
    """Cross-cutting auth tests for the API key middleware."""

    def setup_method(self):
        reset_search_backend()
        reset_stores()

    def teardown_method(self):
        reset_stores()

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch):
        """Ensure DOLPHIN_API_KEY is cleared before each test."""
        monkeypatch.delenv("DOLPHIN_API_KEY", raising=False)
        monkeypatch.delenv("DOLPHIN_KB_API_KEY", raising=False)

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/v1/repos"),
            ("POST", "/v1/search"),
            ("GET", "/v1/chunks/test-id"),
            ("POST", "/v1/index"),
            ("GET", "/v1/index/tasks"),
        ],
    )
    def test_protected_routes_reject_missing_key(self, method, path, monkeypatch):
        """All /v1 routes (except health) require an API key."""
        monkeypatch.setenv("DOLPHIN_API_KEY", "real-key")
        client = TestClient(app)
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/v1/repos"),
            ("POST", "/v1/search"),
            ("GET", "/v1/index/tasks"),
        ],
    )
    def test_protected_routes_reject_wrong_key(self, method, path, monkeypatch):
        """Wrong API key is rejected."""
        monkeypatch.setenv("DOLPHIN_API_KEY", "real-key")
        client = TestClient(app)
        client.headers = {"X-API-Key": "bad-key"}
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 401

    def test_health_allowed_without_key(self, monkeypatch):
        """Health endpoint does not require an API key."""
        monkeypatch.setenv("DOLPHIN_API_KEY", "some-key")
        client = TestClient(app)
        resp = client.get("/v1/health")
        assert resp.status_code == 200

    def test_accepts_env_key(self, monkeypatch):
        """Primary env var DOLPHIN_API_KEY is accepted."""
        monkeypatch.setenv("DOLPHIN_API_KEY", "my-key")
        client = TestClient(app)
        resp = client.get("/v1/index/tasks", headers={"X-API-Key": "my-key"})
        assert resp.status_code == 200

    def test_accepts_legacy_env_key(self, monkeypatch):
        """Legacy env var DOLPHIN_KB_API_KEY is accepted."""
        monkeypatch.setenv("DOLPHIN_KB_API_KEY", "legacy-key")
        client = TestClient(app)
        resp = client.get("/v1/index/tasks", headers={"X-API-Key": "legacy-key"})
        assert resp.status_code == 200
