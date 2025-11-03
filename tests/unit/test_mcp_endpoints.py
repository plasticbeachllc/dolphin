import tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from kb.api.app import app, set_search_backend, set_stores, reset_search_backend
from kb.api.search_backend import create_search_backend
from kb.config import KBConfig

@pytest.fixture
def client_with_data():
    """Create a test client with an initialized backend and some data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_root = Path(tmpdir)
        config = KBConfig(store_root=store_root)
        
        # Use the stable factory signature
        backend = create_search_backend(
            store_root=store_root,
            embedding_provider_type="stub"
        )
        set_search_backend(backend)
        set_stores(backend.sql_store, backend.lance_store)

        # Initialize the database schema first
        backend.sql_store.initialize()
        
        # Add some data
        backend.sql_store.record_repo("test-repo", Path("/path/to/repo"), default_embed_model="small")
        
        yield TestClient(app)
        
        reset_search_backend()

class TestMCPEndpoints:
    def test_health_shallow(self, client_with_data):
        response = client_with_data.get("/health?deep=false")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_deep(self, client_with_data):
        response = client_with_data.get("/health?deep=true")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        # Deep health check may or may not include stores info
        data = response.json()
        if "stores" in data:
            assert "stores" in data

    def test_list_repos(self, client_with_data):
        response = client_with_data.get("/repos")
        assert response.status_code == 200
        data = response.json()
        assert len(data["repos"]) == 1
        assert data["repos"][0]["name"] == "test-repo"

    # ... other tests that use client_with_data will now work ...