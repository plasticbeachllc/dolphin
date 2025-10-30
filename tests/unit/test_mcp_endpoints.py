"""Tests for MCP-required API endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pb_kb.api.app import app, set_search_backend, set_stores, reset_search_backend, reset_stores
from pb_kb.api.search_backend import create_search_backend
from pb_kb.store.sqlite_meta import SQLiteMetadataStore


class TestMCPEndpoints:
    """Tests for endpoints required by MCP Bridge."""

    @pytest.fixture
    def client_with_data(self):
        """Create a test client with indexed data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir)

            # Create backend
            backend = create_search_backend(store_root, embedding_provider_type="stub")
            backend.lance_store.initialize_collections()
            backend.sql_store.initialize()

            # Register a test repo
            test_repo_path = Path(tmpdir) / "test_repo"
            test_repo_path.mkdir()
            backend.sql_store.record_repo("test-repo", test_repo_path)

            # Create a test file
            test_file = test_repo_path / "test.py"
            test_file.write_text("def hello():\n    print('world')\n")

            # Insert test chunks
            chunks = [
                {
                    "id": "chunk-abc123",
                    "vector": [0.1] * 1536,
                    "repo": "test-repo",
                    "path": "test.py",
                    "start_line": 1,
                    "end_line": 2,
                    "text_hash": "hash1",
                    "commit": "abc123",
                    "branch": "main",
                    "embed_model": "small",
                    "language": "python",
                    "symbol_kind": "function",
                    "symbol_name": "hello",
                    "symbol_path": "hello",
                    "token_count": 10,
                }
            ]
            backend.lance_store.upsert_chunks("test-repo", chunks, model="small")

            # Set for API
            set_search_backend(backend)
            set_stores(backend.sql_store, backend.lance_store)

            client = TestClient(app)
            yield client

            # Cleanup
            reset_search_backend()

    def test_health_shallow(self):
        """Test shallow health check."""
        client = TestClient(app)
        response = client.get("/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_deep(self, client_with_data):
        """Test deep health check."""
        response = client_with_data.get("/v1/health?check=deep")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "checks" in data
        assert "lancedb" in data["checks"]
        assert "embeddings" in data["checks"]

    def test_list_repos(self, client_with_data):
        """Test listing repositories."""
        response = client_with_data.get("/v1/repos")

        assert response.status_code == 200
        data = response.json()

        assert "repos" in data
        assert len(data["repos"]) >= 1

        repo = data["repos"][0]
        assert "name" in repo
        assert "path" in repo
        assert "default_embed_model" in repo
        assert "files" in repo
        assert "chunks" in repo

        assert repo["name"] == "test-repo"

    def test_fetch_chunk(self, client_with_data):
        """Test fetching a chunk by ID."""
        response = client_with_data.get("/v1/chunks/chunk-abc123")

        assert response.status_code == 200
        data = response.json()

        assert data["chunk_id"] == "chunk-abc123"
        assert data["repo"] == "test-repo"
        assert data["path"] == "test.py"
        assert data["start_line"] == 1
        assert data["end_line"] == 2
        assert data["language"] == "python"
        assert data["symbol_name"] == "hello"

    def test_fetch_chunk_not_found(self, client_with_data):
        """Test fetching non-existent chunk."""
        response = client_with_data.get("/v1/chunks/nonexistent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_fetch_file_slice(self, client_with_data):
        """Test fetching file content by line range."""
        response = client_with_data.get(
            "/v1/file",
            params={
                "repo": "test-repo",
                "path": "test.py",
                "start": 1,
                "end": 2
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["repo"] == "test-repo"
        assert data["path"] == "test.py"
        assert data["start_line"] == 1
        assert data["end_line"] == 2
        assert "def hello():" in data["content"]
        assert data["total_lines"] == 2

    def test_fetch_file_entire_file(self, client_with_data):
        """Test fetching entire file."""
        response = client_with_data.get(
            "/v1/file",
            params={
                "repo": "test-repo",
                "path": "test.py",
                "start": 1,
                "end": 1000  # Beyond file length
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "def hello():" in data["content"]
        assert "print('world')" in data["content"]

    def test_fetch_file_invalid_repo(self, client_with_data):
        """Test fetching file from non-existent repo."""
        response = client_with_data.get(
            "/v1/file",
            params={
                "repo": "nonexistent-repo",
                "path": "test.py",
                "start": 1,
                "end": 10
            }
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_fetch_file_not_found(self, client_with_data):
        """Test fetching non-existent file."""
        response = client_with_data.get(
            "/v1/file",
            params={
                "repo": "test-repo",
                "path": "nonexistent.py",
                "start": 1,
                "end": 10
            }
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_fetch_file_path_traversal_blocked(self, client_with_data):
        """Test that path traversal attacks are blocked."""
        response = client_with_data.get(
            "/v1/file",
            params={
                "repo": "test-repo",
                "path": "../../../etc/passwd",
                "start": 1,
                "end": 10
            }
        )

        # Should be blocked (400 Bad Request, 403 Forbidden, or 404 Not Found)
        assert response.status_code in [400, 403, 404]

    def test_repos_without_store(self):
        """Test repos endpoint without initialized store."""
        reset_search_backend()
        reset_stores()
        client = TestClient(app)

        response = client.get("/v1/repos")
        assert response.status_code == 503


class TestMCPEndpointsIntegration:
    """Integration tests with real MCP workflow."""

    @pytest.fixture
    def client_with_indexed_repo(self):
        """Create client with a more realistic indexed repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_root = Path(tmpdir)

            # Create backend
            backend = create_search_backend(store_root, embedding_provider_type="stub")
            backend.lance_store.initialize_collections()
            backend.sql_store.initialize()

            # Register repo
            test_repo_path = Path(tmpdir) / "myproject"
            test_repo_path.mkdir()
            (test_repo_path / "src").mkdir()
            backend.sql_store.record_repo("myproject", test_repo_path)

            # Create multiple files
            (test_repo_path / "src" / "main.py").write_text(
                "def main():\n    print('Hello')\n    return 0\n"
            )
            (test_repo_path / "README.md").write_text(
                "# MyProject\n\nA test project.\n"
            )

            # Insert chunks
            chunks = [
                {
                    "id": "main-func",
                    "vector": [0.1] * 1536,
                    "repo": "myproject",
                    "path": "src/main.py",
                    "start_line": 1,
                    "end_line": 3,
                    "text_hash": "hash-main",
                    "commit": "abc123",
                    "branch": "main",
                    "embed_model": "small",
                    "language": "python",
                    "symbol_kind": "function",
                    "symbol_name": "main",
                    "symbol_path": "main",
                    "token_count": 15,
                },
                {
                    "id": "readme",
                    "vector": [0.2] * 1536,
                    "repo": "myproject",
                    "path": "README.md",
                    "start_line": 1,
                    "end_line": 3,
                    "text_hash": "hash-readme",
                    "commit": "abc123",
                    "branch": "main",
                    "embed_model": "small",
                    "language": "markdown",
                    "token_count": 8,
                },
            ]
            backend.lance_store.upsert_chunks("myproject", chunks, model="small")

            # Set for API
            set_search_backend(backend)
            set_stores(backend.sql_store, backend.lance_store)

            client = TestClient(app)
            yield client

            reset_search_backend()

    def test_mcp_workflow(self, client_with_indexed_repo):
        """Test a complete MCP workflow: list repos -> search -> fetch chunk -> fetch file."""
        # 1. List repos
        repos_response = client_with_indexed_repo.get("/v1/repos")
        assert repos_response.status_code == 200
        repos = repos_response.json()["repos"]
        assert len(repos) >= 1
        assert repos[0]["name"] == "myproject"

        # 2. Search for code
        search_response = client_with_indexed_repo.post(
            "/v1/search",
            json={"query": "main function", "repos": ["myproject"], "top_k": 5}
        )
        assert search_response.status_code == 200
        hits = search_response.json()["hits"]
        assert len(hits) >= 1

        # 3. Fetch chunk details
        chunk_id = "main-func"
        chunk_response = client_with_indexed_repo.get(f"/v1/chunks/{chunk_id}")
        assert chunk_response.status_code == 200
        chunk = chunk_response.json()
        assert chunk["repo"] == "myproject"
        assert chunk["path"] == "src/main.py"

        # 4. Fetch file content
        file_response = client_with_indexed_repo.get(
            "/v1/file",
            params={
                "repo": "myproject",
                "path": "src/main.py",
                "start": 1,
                "end": 3
            }
        )
        assert file_response.status_code == 200
        file_data = file_response.json()
        assert "def main():" in file_data["content"]
        assert "Hello" in file_data["content"]
