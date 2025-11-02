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

        # Add some data
        backend.sql_store.register_repo("test-repo", "small", "/path/to/repo")
        backend.sql_store.add_file("test-repo", "src/main.py", 100)
        
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
        assert "stores" in response.json()

    def test_list_repos(self, client_with_data):
        response = client_with_data.get("/repos/list")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "test-repo"

    # ... other tests that use client_with_data will now work ...