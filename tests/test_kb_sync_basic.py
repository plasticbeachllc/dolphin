"""
Basic integration tests for KB auto-sync functionality.

Run with: pytest tests/test_kb_sync_basic.py -v
"""

import pytest
import time
import tempfile
import shutil
from pathlib import Path
import requests

KB_API_URL = "http://localhost:7777"


@pytest.fixture
def test_workspace():
    """Create a temporary test workspace."""
    temp_dir = tempfile.mkdtemp(prefix="kb-test-")
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def registered_repo(test_workspace):
    """Register a test repository with KB API."""
    repo_name = Path(test_workspace).name

    response = requests.post(
        f"{KB_API_URL}/v1/repos",
        json={
            "name": repo_name,
            "path": test_workspace,
            "default_embed_model": "large"
        }
    )

    assert response.status_code == 200
    data = response.json()

    yield {
        "name": repo_name,
        "path": test_workspace,
        "repo_id": data["repo_id"]
    }


class TestKBAPI:
    """Test KB API endpoints."""

    def test_health_check(self):
        """Test /health endpoint."""
        response = requests.get(f"{KB_API_URL}/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_deep_health_check(self):
        """Test /health endpoint with deep check."""
        response = requests.get(f"{KB_API_URL}/health?check=deep")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "checks" in data

    def test_register_repo(self, test_workspace):
        """Test POST /v1/repos endpoint."""
        repo_name = Path(test_workspace).name

        response = requests.post(
            f"{KB_API_URL}/v1/repos",
            json={
                "name": repo_name,
                "path": test_workspace,
                "default_embed_model": "large"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == repo_name
        assert "repo_id" in data
        assert data["path"] == test_workspace

    def test_list_repos(self, registered_repo):
        """Test GET /repos endpoint."""
        response = requests.get(f"{KB_API_URL}/repos")

        assert response.status_code == 200
        data = response.json()

        assert "repos" in data
        assert isinstance(data["repos"], list)

        # Find our test repo
        test_repo = next(
            (r for r in data["repos"] if r["name"] == registered_repo["name"]),
            None
        )
        assert test_repo is not None


class TestAsyncIndexing:
    """Test async indexing functionality."""

    def test_queue_indexing(self, registered_repo):
        """Test POST /v1/index creates task."""
        # Create test files
        workspace = Path(registered_repo["path"])
        test_file = workspace / "test.py"
        test_file.write_text("def hello(): return 'world'")

        # Queue indexing
        response = requests.post(
            f"{KB_API_URL}/v1/index",
            json={
                "repo": registered_repo["name"],
                "files": ["test.py"],
                "incremental": True
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert "task_id" in data
        assert data["status"] == "queued"
        assert "message" in data

    def test_get_task_status(self, registered_repo):
        """Test GET /v1/index/status/{task_id}."""
        # Create and queue file
        workspace = Path(registered_repo["path"])
        test_file = workspace / "status_test.py"
        test_file.write_text("x = 1")

        queue_response = requests.post(
            f"{KB_API_URL}/v1/index",
            json={
                "repo": registered_repo["name"],
                "files": ["status_test.py"]
            }
        )

        task_id = queue_response.json()["task_id"]

        # Get status
        status_response = requests.get(f"{KB_API_URL}/v1/index/status/{task_id}")

        assert status_response.status_code == 200
        data = status_response.json()

        assert data["task_id"] == task_id
        assert data["status"] in ["queued", "processing", "completed", "failed"]
        assert "progress" in data
        assert "total" in data

    def test_list_tasks(self, registered_repo):
        """Test GET /v1/index/tasks."""
        response = requests.get(f"{KB_API_URL}/v1/index/tasks")

        assert response.status_code == 200
        data = response.json()

        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    def test_list_tasks_filtered_by_repo(self, registered_repo):
        """Test GET /v1/index/tasks with repo filter."""
        response = requests.get(
            f"{KB_API_URL}/v1/index/tasks",
            params={"repo": registered_repo["name"]}
        )

        assert response.status_code == 200
        data = response.json()

        assert "tasks" in data
        # All tasks should be for this repo
        for task in data["tasks"]:
            assert task["repo"] == registered_repo["name"]

    def test_indexing_completion(self, registered_repo):
        """Test full indexing flow from queue to completion."""
        # Create test file
        workspace = Path(registered_repo["path"])
        test_file = workspace / "complete_test.ts"
        test_file.write_text("""
export class TestClass {
  private value: number = 42;
  getValue(): number { return this.value; }
}
""")

        # Queue indexing
        queue_response = requests.post(
            f"{KB_API_URL}/v1/index",
            json={
                "repo": registered_repo["name"],
                "files": ["complete_test.ts"]
            }
        )

        task_id = queue_response.json()["task_id"]

        # Poll for completion (max 30 seconds)
        max_polls = 30
        final_status = None

        for _ in range(max_polls):
            status_response = requests.get(f"{KB_API_URL}/v1/index/status/{task_id}")
            status = status_response.json()

            if status["status"] in ["completed", "failed"]:
                final_status = status
                break

            time.sleep(1)

        # Verify completion
        assert final_status is not None, "Indexing did not complete within 30 seconds"
        assert final_status["status"] == "completed", f"Indexing failed: {final_status.get('error')}"
        assert final_status["total"] == 1

    def test_multiple_files(self, registered_repo):
        """Test indexing multiple files in one batch."""
        workspace = Path(registered_repo["path"])

        # Create multiple files
        files = []
        for i in range(5):
            filename = f"file{i}.py"
            file_path = workspace / filename
            file_path.write_text(f"def func{i}(): return {i}")
            files.append(filename)

        # Queue all files
        queue_response = requests.post(
            f"{KB_API_URL}/v1/index",
            json={
                "repo": registered_repo["name"],
                "files": files
            }
        )

        assert queue_response.status_code == 200
        task_id = queue_response.json()["task_id"]

        # Wait for completion
        for _ in range(30):
            status = requests.get(f"{KB_API_URL}/v1/index/status/{task_id}").json()
            if status["status"] in ["completed", "failed"]:
                break
            time.sleep(1)

        assert status["status"] == "completed"
        assert status["total"] == 5


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_repo(self):
        """Test indexing non-existent repo."""
        response = requests.post(
            f"{KB_API_URL}/v1/index",
            json={
                "repo": "nonexistent-repo-12345",
                "files": ["test.py"]
            }
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_invalid_task_id(self):
        """Test getting status of non-existent task."""
        response = requests.get(f"{KB_API_URL}/v1/index/status/invalid-task-id-12345")

        assert response.status_code == 404

    def test_empty_file_list(self, registered_repo):
        """Test indexing with empty file list."""
        response = requests.post(
            f"{KB_API_URL}/v1/index",
            json={
                "repo": registered_repo["name"],
                "files": []
            }
        )

        # Should still create task, but complete immediately
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
