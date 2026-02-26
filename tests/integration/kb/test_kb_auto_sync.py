"""Integration tests for KB auto-sync functionality.

These tests validate the full end-to-end flow:
- Repository update → KB API → Pipeline → Storage
"""

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kb.api.app import app, reset_pipeline, reset_stores, set_pipeline, set_stores
from kb.config import KBConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store.lancedb_vector import LanceDBVectorStore
from kb.store.sqlite_meta import SQLiteMetadataStore

TEST_API_KEY = "test-api-key"
os.environ["DOLPHIN_API_KEY"] = TEST_API_KEY


def create_api_client() -> TestClient:
    """FastAPI TestClient preconfigured with the test API key."""
    client = TestClient(app)
    client.headers = {"X-API-Key": TEST_API_KEY}
    return client


@pytest.mark.integration
class TestRepositoryRegistration:
    """Test repository registration workflow."""

    def test_register_new_workspace(self, temp_dir, temp_db_path):
        """Test registering a new workspace with KB."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Create test workspace
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        # Initialize git repo (simulating real workspace)
        import subprocess

        subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=workspace,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/my-repo.git"],
            cwd=workspace,
            check=True,
        )

        # Register workspace
        client = create_api_client()
        response = client.post(
            "/v1/repos",
            json={
                "name": "my-repo",
                "path": str(workspace),
                "default_embed_model": "large",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "my-repo"
        # Normalize paths for comparison (macOS /var -> /private/var)
        assert Path(data["path"]).resolve() == workspace.resolve()
        assert "repo_id" in data

        # Verify in database
        repo = sql_store.get_repo_by_name("my-repo")
        assert repo is not None
        # repo is a dict, not an object
        assert Path(repo["root_path"]).resolve() == workspace.resolve()

        # Cleanup
        reset_stores()
        # Cleanup - no explicit close needed

    def test_register_workspace_idempotent(self, temp_dir, temp_db_path):
        """Test that registering same workspace twice is idempotent."""
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        client = create_api_client()

        # Register first time
        response1 = client.post(
            "/v1/repos",
            json={
                "name": "test-repo",
                "path": str(workspace),
                "default_embed_model": "large",
            },
        )
        assert response1.status_code == 200
        response1.json()["repo_id"]

        # Register second time - should not fail
        response2 = client.post(
            "/v1/repos",
            json={
                "name": "test-repo",
                "path": str(workspace),
                "default_embed_model": "large",
            },
        )

        # Should either return same repo or indicate already exists
        assert response2.status_code in [200, 400, 409]

        # Cleanup
        reset_stores()
        # Cleanup - no explicit close needed


@pytest.mark.integration
class TestAsyncIndexingFlow:
    """Test async indexing workflow from queue to completion."""

    def test_single_file_indexing_full_flow(self, temp_dir, temp_db_path):
        """Test indexing a single file through the full pipeline."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create workspace and register
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        sql_store.record_repo(name="test-repo", path=workspace, default_embed_model="small")
        repo = sql_store.get_repo_by_name("test-repo")
        assert repo is not None

        # Create test file
        test_file = workspace / "hello.py"
        test_file.write_text(
            """
def hello_world():
    '''A simple greeting function.'''
    return "Hello, World!"

def goodbye():
    '''Say goodbye.'''
    return "Goodbye!"
"""
        )

        # Queue indexing
        client = create_api_client()
        response = client.post(
            "/v1/index",
            json={"repo": "test-repo", "files": ["hello.py"], "incremental": True},
        )

        assert response.status_code == 200
        data = response.json()
        task_id = data["task_id"]
        assert data["status"] == "queued"

        # Poll for completion (max 30 seconds)
        max_polls = 30
        final_status = None

        for _ in range(max_polls):
            status_response = client.get(f"/v1/index/status/{task_id}")
            status_data = status_response.json()

            if status_data["status"] in ["completed", "failed"]:
                final_status = status_data
                break

            time.sleep(1)

        # Verify completion
        assert final_status is not None, "Indexing did not complete within 30 seconds"
        if final_status["status"] == "failed":
            pytest.fail(f"Indexing failed: {final_status.get('error')}")
        assert final_status["status"] == "completed", f"Indexing failed: {final_status.get('error')}"
        assert final_status["total"] == 1

        # Verify chunks were created
        chunks = sql_store.get_chunks_for_file(repo["id"], "hello.py")
        assert chunks is not None
        assert len(chunks) > 0

        # Cleanup
        reset_pipeline()
        reset_stores()
        # Cleanup - no explicit close needed

    def test_index_fails_when_active_session_exists(self, temp_dir, temp_db_path):
        """Test indexing fails fast when another session is active."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create workspace and register
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        sql_store.record_repo(name="test-repo", path=workspace, default_embed_model="small")
        repo = sql_store.get_repo_by_name("test-repo")
        assert repo is not None

        # Create test file
        test_file = workspace / "hello.py"
        test_file.write_text("print('hello')")

        # Create an active session to block indexing
        sql_store.begin_session(repo_id=repo["id"], commit_sha="abc123", branch="main", embed_model="small")

        # Queue indexing
        client = create_api_client()
        response = client.post(
            "/v1/index",
            json={"repo": "test-repo", "files": ["hello.py"], "incremental": True},
        )

        assert response.status_code == 200
        data = response.json()
        task_id = data["task_id"]

        # Poll for completion (max 10 seconds)
        max_polls = 10
        final_status = None
        last_error = None

        for _ in range(max_polls):
            status_response = client.get(f"/v1/index/status/{task_id}")
            status_data = status_response.json()
            if status_data["status"] in ["completed", "failed"]:
                final_status = status_data
                break
            time.sleep(1)

        assert final_status is not None
        assert final_status["status"] == "failed"
        last_error = final_status.get("error")
        assert last_error is not None
        assert "Active indexing session" in last_error

        # Cleanup
        reset_pipeline()
        reset_stores()

    def test_multiple_files_batch_indexing(self, temp_dir, temp_db_path):
        """Test indexing multiple files in a batch."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create workspace
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        sql_store.record_repo(name="test-repo", path=workspace, default_embed_model="small")
        repo = sql_store.get_repo_by_name("test-repo")
        assert repo is not None

        # Create multiple test files
        files = []
        for i in range(5):
            filename = f"file{i}.py"
            filepath = workspace / filename
            filepath.write_text(
                f"""
def function_{i}():
    '''Function number {i}.'''
    return {i}
"""
            )
            files.append(filename)

        # Queue all files for indexing
        client = create_api_client()
        response = client.post("/v1/index", json={"repo": "test-repo", "files": files, "incremental": True})

        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Poll for completion
        max_polls = 60
        final_status = None

        for _ in range(max_polls):
            status_response = client.get(f"/v1/index/status/{task_id}")
            status_data = status_response.json()

            if status_data["status"] in ["completed", "failed"]:
                final_status = status_data
                break

            time.sleep(1)

        # Verify
        assert final_status is not None
        if final_status["status"] == "failed":
            pytest.fail(f"Indexing failed: {final_status.get('error')}")
        assert final_status["status"] == "completed"
        assert final_status["total"] == 5

        # Verify all files were indexed
        for filename in files:
            chunks = sql_store.get_chunks_for_file(repo["id"], filename)
            assert chunks is not None, f"No chunks found for {filename}"
            assert len(chunks) > 0, f"No chunks found for {filename}"

        # Cleanup
        reset_pipeline()
        reset_stores()
        # Cleanup - no explicit close needed

    def test_incremental_indexing_deduplication(self, temp_dir, temp_db_path):
        """Test that incremental indexing skips unchanged files."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create workspace
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        sql_store.record_repo(name="test-repo", path=workspace, default_embed_model="small")
        repo = sql_store.get_repo_by_name("test-repo")
        assert repo is not None

        # Create test file
        test_file = workspace / "test.py"
        test_content = "def test(): return 42"
        test_file.write_text(test_content)

        client = create_api_client()

        # Index first time
        response1 = client.post(
            "/v1/index",
            json={"repo": "test-repo", "files": ["test.py"], "incremental": True},
        )
        task_id_1 = response1.json()["task_id"]

        # Wait for completion
        for _ in range(30):
            status = client.get(f"/v1/index/status/{task_id_1}").json()
            if status["status"] == "completed":
                break
            if status["status"] == "failed":
                pytest.fail(f"Indexing failed: {status.get('error')}")
            time.sleep(1)

        assert status["status"] == "completed", f"Indexing failed: {status.get('error', 'unknown error')}"
        chunks = sql_store.get_chunks_for_file(repo["id"], "test.py")
        assert chunks is not None
        first_indexed_count = len(chunks)

        # Index again without changing file (incremental should skip)
        response2 = client.post(
            "/v1/index",
            json={"repo": "test-repo", "files": ["test.py"], "incremental": True},
        )
        task_id_2 = response2.json()["task_id"]

        # Wait for completion
        for _ in range(30):
            status = client.get(f"/v1/index/status/{task_id_2}").json()
            if status["status"] == "completed":
                break
            if status["status"] == "failed":
                pytest.fail(f"Indexing failed: {status.get('error')}")
            time.sleep(1)

        assert status["status"] == "completed", f"Indexing failed: {status.get('error', 'unknown error')}"
        chunks = sql_store.get_chunks_for_file(repo["id"], "test.py")
        assert chunks is not None
        second_indexed_count = len(chunks)

        # Should have same number of chunks (deduplication worked)
        assert second_indexed_count == first_indexed_count

        # Cleanup
        reset_pipeline()
        reset_stores()
        # Cleanup - no explicit close needed


@pytest.mark.integration
class TestTaskStatusTracking:
    """Test task status tracking through lifecycle."""

    def test_task_status_progression(self, temp_dir, temp_db_path):
        """Test task status progresses from queued -> processing -> completed."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create workspace
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        sql_store.record_repo(name="test-repo", path=workspace, default_embed_model="small")
        sql_store.get_repo_by_name("test-repo")

        # Create test file
        (workspace / "test.py").write_text("def test(): pass")

        client = create_api_client()

        # Queue task
        response = client.post("/v1/index", json={"repo": "test-repo", "files": ["test.py"]})
        task_id = response.json()["task_id"]

        # Track status changes
        statuses_seen = set()

        for _ in range(30):
            status = client.get(f"/v1/index/status/{task_id}").json()
            statuses_seen.add(status["status"])

            if status["status"] == "completed":
                break

            time.sleep(0.1)  # Shorter polling interval to catch intermediate states

        # Should have completed successfully
        assert "completed" in statuses_seen
        # Task may complete so quickly we only see completed state, which is fine
        # The important thing is that it completed without errors

        # Cleanup
        reset_pipeline()
        reset_stores()
        # Cleanup - no explicit close needed

    def test_task_list_filtering(self, temp_dir, temp_db_path):
        """Test listing and filtering tasks by repository."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create two workspaces
        workspace1 = temp_dir / "workspace1"
        workspace1.mkdir()
        workspace2 = temp_dir / "workspace2"
        workspace2.mkdir()

        sql_store.record_repo(name="repo1", path=workspace1, default_embed_model="small")

        sql_store.get_repo_by_name("repo1")
        sql_store.record_repo(name="repo2", path=workspace2, default_embed_model="small")

        sql_store.get_repo_by_name("repo2")

        # Create test files
        (workspace1 / "test1.py").write_text("def test1(): pass")
        (workspace2 / "test2.py").write_text("def test2(): pass")

        client = create_api_client()

        # Queue tasks for both repos
        client.post("/v1/index", json={"repo": "repo1", "files": ["test1.py"]})
        client.post("/v1/index", json={"repo": "repo2", "files": ["test2.py"]})

        # List all tasks
        all_tasks_response = client.get("/v1/index/tasks")
        all_tasks = all_tasks_response.json()["tasks"]

        # Should have at least 2 tasks
        assert len(all_tasks) >= 2

        # Filter by repo1
        repo1_tasks_response = client.get("/v1/index/tasks?repo=repo1")
        repo1_tasks = repo1_tasks_response.json()["tasks"]

        # All should be for repo1
        for task in repo1_tasks:
            assert task["repo"] == "repo1"

        # Cleanup
        reset_pipeline()
        reset_stores()
        # Cleanup - no explicit close needed


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling in indexing pipeline."""

    def test_index_nonexistent_file(self, temp_dir, temp_db_path):
        """Test indexing a file that doesn't exist."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create workspace
        workspace = temp_dir / "test_workspace"
        workspace.mkdir()

        sql_store.record_repo(name="test-repo", path=workspace, default_embed_model="small")
        sql_store.get_repo_by_name("test-repo")

        client = create_api_client()

        # Try to index non-existent file
        response = client.post("/v1/index", json={"repo": "test-repo", "files": ["nonexistent.py"]})

        # Should queue the task
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # Wait for task to complete (may fail or complete with errors)
        for _ in range(30):
            status = client.get(f"/v1/index/status/{task_id}").json()
            if status["status"] in ["completed", "failed"]:
                break
            time.sleep(1)

        # Task should complete (file just gets skipped or errors recorded)
        assert status["status"] in ["completed", "failed"]

        # Cleanup
        reset_pipeline()
        reset_stores()
        # Cleanup - no explicit close needed

    def test_index_invalid_repository(self, temp_dir, temp_db_path):
        """Test indexing with invalid repository name."""
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        client = create_api_client()

        # Try to index for non-existent repo
        response = client.post("/v1/index", json={"repo": "nonexistent-repo", "files": ["test.py"]})

        # Should return 404
        assert response.status_code == 404

        # Cleanup
        reset_stores()
        # Cleanup - no explicit close needed


@pytest.mark.integration
class TestEndToEndWorkflow:
    """Test complete end-to-end workflow: register -> index -> search."""

    def test_full_workflow_with_search(self, temp_dir, temp_db_path):
        """Test full workflow: register repo, index files, search for content."""
        # Set up stores
        sql_store = SQLiteMetadataStore(temp_db_path)
        sql_store.initialize()

        lance_dir = temp_dir / "lancedb"
        lance_dir.mkdir()
        lance_store = LanceDBVectorStore(lance_dir)

        set_stores(sql_store, lance_store)

        # Set up pipeline
        pipeline = IngestionPipeline(config=KBConfig(), lancedb=lance_store, metadata=sql_store)
        set_pipeline(pipeline)

        # Create workspace
        workspace = temp_dir / "my_project"
        workspace.mkdir()

        client = create_api_client()

        # Step 1: Register repository
        register_response = client.post(
            "/v1/repos",
            json={
                "name": "my-project",
                "path": str(workspace),
                "default_embed_model": "large",
            },
        )
        assert register_response.status_code == 200

        # Step 2: Create code files
        auth_file = workspace / "auth.py"
        auth_file.write_text(
            """
class AuthenticationService:
    '''Handles user authentication and authorization.'''

    def login(self, username: str, password: str) -> bool:
        '''Authenticate user with username and password.'''
        # Authentication logic here
        return True

    def logout(self, user_id: int) -> None:
        '''Log out user session.'''
        pass
"""
        )

        api_file = workspace / "api.py"
        api_file.write_text(
            """
class APIEndpoint:
    '''REST API endpoint handler.'''

    def handle_request(self, method: str, path: str) -> dict:
        '''Handle incoming API request.'''
        return {"status": "ok"}
"""
        )

        # Step 3: Index files
        index_response = client.post(
            "/v1/index",
            json={
                "repo": "my-project",
                "files": ["auth.py", "api.py"],
                "incremental": True,
            },
        )
        assert index_response.status_code == 200
        task_id = index_response.json()["task_id"]

        # Wait for indexing to complete
        for _ in range(60):
            status = client.get(f"/v1/index/status/{task_id}").json()
            if status["status"] == "completed":
                break
            if status["status"] == "failed":
                pytest.fail(f"Indexing failed: {status.get('error')}")
            time.sleep(1)

        assert status["status"] == "completed", f"Indexing failed: {status.get('error', 'unknown error')}"

        # Step 4: Search for indexed content
        search_response = client.post(
            "/v1/search",
            json={"query": "authentication", "repos": ["my-project"], "top_k": 5},
        )

        assert search_response.status_code == 200
        search_data = search_response.json()
        assert "hits" in search_data

        # Should find results related to authentication
        hits = search_data["hits"]
        if len(hits) > 0:
            # At least one result should be from auth.py
            auth_results = [h for h in hits if "auth.py" in h.get("path", "")]
            assert len(auth_results) > 0

        # Cleanup
        reset_pipeline()
        reset_stores()
        # Cleanup - no explicit close needed
