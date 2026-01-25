import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from kb.api.app import app, reset_search_backend, set_search_backend
from kb.api.search_backend import create_search_backend


@pytest.fixture
def client_with_backend():
    """Create a test client with a real, but stubbed, search backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir)
        backend = create_search_backend(store_root=store_root)
        set_search_backend(backend)
        prev = os.environ.get("DOLPHIN_API_KEY")
        os.environ["DOLPHIN_API_KEY"] = "test-api-key"
        client = TestClient(app)
        client.headers = {"X-API-Key": "test-api-key"}
        try:
            yield client
        finally:
            if prev is None:
                os.environ.pop("DOLPHIN_API_KEY", None)
            else:
                os.environ["DOLPHIN_API_KEY"] = prev
        reset_search_backend()


class TestSearchAPI:
    def test_health_endpoint(self, client_with_backend):
        response = client_with_backend.get("/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_search_basic(self, client_with_backend):
        with patch("kb.api.app.get_search_backend") as mock_get_backend:
            mock_backend = MagicMock()
            mock_backend.search.return_value = [{"chunk_id": "1"}]
            mock_get_backend.return_value = mock_backend

            response = client_with_backend.post("/v1/search", json={"query": "test"})
            assert response.status_code == 200
            response_data = response.json()
            assert "hits" in response_data
            assert response_data["hits"] == [{"chunk_id": "1"}]
            mock_backend.search.assert_called_once()

    def test_search_invalid_request(self, client_with_backend):
        response = client_with_backend.post("/v1/search", json={"top_k": 5})
        assert response.status_code == 422
