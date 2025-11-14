"""Unit tests for TaskQueue functionality."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from kb.api.task_queue import TaskStatus


class TestTaskQueueCreation:
    """Test task creation and initialization."""

    def test_create_task_basic(self, task_queue_instance):
        """Test creating a basic indexing task."""
        queue = task_queue_instance

        task = queue.create_task(repo="test-repo", files=["file1.py", "file2.py"])

        assert task.task_id is not None
        assert task.repo == "test-repo"
        assert task.files == ["file1.py", "file2.py"]
        assert task.status == TaskStatus.QUEUED
        assert task.progress == 0
        assert task.total == 2
        assert task.error is None
        assert task.result is None
        assert task.created_at is not None
        assert task.started_at is None
        assert task.completed_at is None

    def test_create_task_empty_files(self, task_queue_instance):
        """Test creating task with empty file list."""
        queue = task_queue_instance

        task = queue.create_task(repo="test-repo", files=[])

        assert task.total == 0
        assert task.files == []

    def test_create_task_stored_in_queue(self, task_queue_instance):
        """Test that created task is stored in queue."""
        queue = task_queue_instance

        task = queue.create_task(repo="test-repo", files=["file.py"])

        assert task.task_id in queue.tasks
        assert queue.tasks[task.task_id] == task

    def test_create_multiple_tasks_unique_ids(self, task_queue_instance):
        """Test that multiple tasks get unique IDs."""
        queue = task_queue_instance

        task1 = queue.create_task(repo="repo1", files=["a.py"])
        task2 = queue.create_task(repo="repo2", files=["b.py"])

        assert task1.task_id != task2.task_id
        assert len(queue.tasks) == 2


class TestTaskQueueRetrieval:
    """Test task retrieval operations."""

    def test_get_task_exists(self, task_queue_instance):
        """Test retrieving an existing task."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["file.py"])

        retrieved = queue.get_task(task.task_id)

        assert retrieved is not None
        assert retrieved.task_id == task.task_id
        assert retrieved.repo == "test-repo"

    def test_get_task_not_exists(self, task_queue_instance):
        """Test retrieving non-existent task returns None."""
        queue = task_queue_instance

        retrieved = queue.get_task("nonexistent-task-id")

        assert retrieved is None

    def test_get_all_tasks_empty(self, task_queue_instance):
        """Test getting all tasks when queue is empty."""
        queue = task_queue_instance

        tasks = queue.get_all_tasks()

        assert tasks == []

    def test_get_all_tasks(self, task_queue_instance):
        """Test getting all tasks."""
        queue = task_queue_instance

        task1 = queue.create_task(repo="repo1", files=["a.py"])
        task2 = queue.create_task(repo="repo2", files=["b.py"])
        task3 = queue.create_task(repo="repo1", files=["c.py"])

        all_tasks = queue.get_all_tasks()

        assert len(all_tasks) == 3
        # Should be sorted by created_at descending (newest first)
        assert all_tasks[0].task_id == task3.task_id
        assert all_tasks[1].task_id == task2.task_id
        assert all_tasks[2].task_id == task1.task_id

    def test_get_all_tasks_filtered_by_repo(self, task_queue_instance):
        """Test getting tasks filtered by repository."""
        queue = task_queue_instance

        queue.create_task(repo="repo-a", files=["a.py"])
        queue.create_task(repo="repo-b", files=["b.py"])
        queue.create_task(repo="repo-a", files=["c.py"])

        repo_a_tasks = queue.get_all_tasks(repo="repo-a")

        assert len(repo_a_tasks) == 2
        assert all(t.repo == "repo-a" for t in repo_a_tasks)

    def test_get_all_tasks_filtered_nonexistent_repo(self, task_queue_instance):
        """Test filtering by repo that has no tasks."""
        queue = task_queue_instance

        queue.create_task(repo="repo-a", files=["a.py"])
        queue.create_task(repo="repo-b", files=["b.py"])

        tasks = queue.get_all_tasks(repo="nonexistent-repo")

        assert tasks == []


class TestTaskQueueUpdate:
    """Test task update operations."""

    @pytest.mark.asyncio
    async def test_update_task_status_to_processing(self, task_queue_instance):
        """Test updating task status to PROCESSING."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["file.py"])

        await queue.update_task(task.task_id, status=TaskStatus.PROCESSING)

        updated = queue.get_task(task.task_id)
        assert updated.status == TaskStatus.PROCESSING
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_update_task_status_to_completed(self, task_queue_instance):
        """Test updating task status to COMPLETED."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["file.py"])

        await queue.update_task(task.task_id, status=TaskStatus.COMPLETED)

        updated = queue.get_task(task.task_id)
        assert updated.status == TaskStatus.COMPLETED
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_task_status_to_failed(self, task_queue_instance):
        """Test updating task status to FAILED."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["file.py"])

        await queue.update_task(task.task_id, status=TaskStatus.FAILED, error="Test error message")

        updated = queue.get_task(task.task_id)
        assert updated.status == TaskStatus.FAILED
        assert updated.error == "Test error message"
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_task_progress(self, task_queue_instance):
        """Test updating task progress."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["a.py", "b.py", "c.py"])

        await queue.update_task(task.task_id, progress=2)

        updated = queue.get_task(task.task_id)
        assert updated.progress == 2
        assert updated.total == 3

    @pytest.mark.asyncio
    async def test_update_task_result(self, task_queue_instance):
        """Test updating task result."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["file.py"])

        result_data = {"indexed": 1, "skipped": 0, "errors": []}
        await queue.update_task(task.task_id, result=result_data)

        updated = queue.get_task(task.task_id)
        assert updated.result == result_data

    @pytest.mark.asyncio
    async def test_update_task_multiple_fields(self, task_queue_instance):
        """Test updating multiple task fields at once."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["a.py", "b.py"])

        await queue.update_task(
            task.task_id,
            status=TaskStatus.COMPLETED,
            progress=2,
            result={"indexed": 2, "skipped": 0},
        )

        updated = queue.get_task(task.task_id)
        assert updated.status == TaskStatus.COMPLETED
        assert updated.progress == 2
        assert updated.result == {"indexed": 2, "skipped": 0}
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_task(self, task_queue_instance):
        """Test updating non-existent task does nothing."""
        queue = task_queue_instance

        # Should not raise exception
        await queue.update_task("nonexistent-id", status=TaskStatus.COMPLETED)

        assert queue.get_task("nonexistent-id") is None

    @pytest.mark.asyncio
    async def test_update_started_at_only_set_once(self, task_queue_instance):
        """Test that started_at is only set on first PROCESSING status."""
        queue = task_queue_instance
        task = queue.create_task(repo="test-repo", files=["file.py"])

        # First update to PROCESSING
        await queue.update_task(task.task_id, status=TaskStatus.PROCESSING)
        first_started = queue.get_task(task.task_id).started_at

        # Wait a bit
        await asyncio.sleep(0.01)

        # Update to PROCESSING again
        await queue.update_task(task.task_id, status=TaskStatus.PROCESSING)
        second_started = queue.get_task(task.task_id).started_at

        # Should be the same timestamp
        assert first_started == second_started


class TestTaskQueueCleanup:
    """Test task cleanup operations."""

    @pytest.mark.asyncio
    async def test_cleanup_old_completed_tasks(self, task_queue_instance):
        """Test cleanup removes old completed tasks."""
        queue = task_queue_instance

        # Create a completed task
        task = queue.create_task(repo="test-repo", files=["file.py"])
        await queue.update_task(task.task_id, status=TaskStatus.COMPLETED)

        # Manually set completed_at to 2 hours ago
        task.completed_at = datetime.now(UTC) - timedelta(hours=2)

        # Cleanup tasks older than 1 hour
        removed = await queue.cleanup_old_tasks(max_age_seconds=3600)

        assert removed == 1
        assert queue.get_task(task.task_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_old_failed_tasks(self, task_queue_instance):
        """Test cleanup removes old failed tasks."""
        queue = task_queue_instance

        # Create a failed task
        task = queue.create_task(repo="test-repo", files=["file.py"])
        await queue.update_task(task.task_id, status=TaskStatus.FAILED, error="Test error")

        # Manually set completed_at to 2 hours ago
        task.completed_at = datetime.now(UTC) - timedelta(hours=2)

        # Cleanup tasks older than 1 hour
        removed = await queue.cleanup_old_tasks(max_age_seconds=3600)

        assert removed == 1
        assert queue.get_task(task.task_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_recent_completed_tasks(self, task_queue_instance):
        """Test cleanup keeps recent completed tasks."""
        queue = task_queue_instance

        # Create a recently completed task
        task = queue.create_task(repo="test-repo", files=["file.py"])
        await queue.update_task(task.task_id, status=TaskStatus.COMPLETED)

        # Cleanup tasks older than 1 hour
        removed = await queue.cleanup_old_tasks(max_age_seconds=3600)

        assert removed == 0
        assert queue.get_task(task.task_id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_queued_tasks(self, task_queue_instance):
        """Test cleanup keeps queued tasks regardless of age."""
        queue = task_queue_instance

        # Create a queued task
        task = queue.create_task(repo="test-repo", files=["file.py"])

        # Manually set created_at to 2 hours ago
        task.created_at = datetime.now(UTC) - timedelta(hours=2)

        # Cleanup
        removed = await queue.cleanup_old_tasks(max_age_seconds=3600)

        assert removed == 0
        assert queue.get_task(task.task_id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_processing_tasks(self, task_queue_instance):
        """Test cleanup keeps processing tasks regardless of age."""
        queue = task_queue_instance

        # Create a processing task
        task = queue.create_task(repo="test-repo", files=["file.py"])
        await queue.update_task(task.task_id, status=TaskStatus.PROCESSING)

        # Manually set started_at to 2 hours ago
        task.started_at = datetime.now(UTC) - timedelta(hours=2)

        # Cleanup
        removed = await queue.cleanup_old_tasks(max_age_seconds=3600)

        assert removed == 0
        assert queue.get_task(task.task_id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_mixed_tasks(self, task_queue_instance):
        """Test cleanup with mixed task states and ages."""
        queue = task_queue_instance

        # Old completed task (should be removed)
        task1 = queue.create_task(repo="repo1", files=["a.py"])
        await queue.update_task(task1.task_id, status=TaskStatus.COMPLETED)
        task1.completed_at = datetime.now(UTC) - timedelta(hours=2)

        # Recent completed task (should be kept)
        task2 = queue.create_task(repo="repo2", files=["b.py"])
        await queue.update_task(task2.task_id, status=TaskStatus.COMPLETED)

        # Processing task (should be kept)
        task3 = queue.create_task(repo="repo3", files=["c.py"])
        await queue.update_task(task3.task_id, status=TaskStatus.PROCESSING)

        # Old failed task (should be removed)
        task4 = queue.create_task(repo="repo4", files=["d.py"])
        await queue.update_task(task4.task_id, status=TaskStatus.FAILED)
        task4.completed_at = datetime.now(UTC) - timedelta(hours=3)

        # Cleanup
        removed = await queue.cleanup_old_tasks(max_age_seconds=3600)

        assert removed == 2
        assert queue.get_task(task1.task_id) is None  # Old completed
        assert queue.get_task(task2.task_id) is not None  # Recent completed
        assert queue.get_task(task3.task_id) is not None  # Processing
        assert queue.get_task(task4.task_id) is None  # Old failed

    @pytest.mark.asyncio
    async def test_cleanup_empty_queue(self, task_queue_instance):
        """Test cleanup on empty queue."""
        queue = task_queue_instance

        removed = await queue.cleanup_old_tasks(max_age_seconds=3600)

        assert removed == 0


class TestTaskQueueConcurrency:
    """Test concurrent access to task queue."""

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, task_queue_instance):
        """Test concurrent updates to different tasks."""
        queue = task_queue_instance

        task1 = queue.create_task(repo="repo1", files=["a.py"])
        task2 = queue.create_task(repo="repo2", files=["b.py"])

        # Update both tasks concurrently
        await asyncio.gather(
            queue.update_task(task1.task_id, status=TaskStatus.PROCESSING),
            queue.update_task(task2.task_id, status=TaskStatus.PROCESSING),
        )

        assert queue.get_task(task1.task_id).status == TaskStatus.PROCESSING
        assert queue.get_task(task2.task_id).status == TaskStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_concurrent_updates_same_task(self, task_queue_instance):
        """Test concurrent updates to the same task (should be serialized by lock)."""
        queue = task_queue_instance

        task = queue.create_task(repo="repo", files=["a.py", "b.py", "c.py"])

        # Update progress concurrently
        await asyncio.gather(
            queue.update_task(task.task_id, progress=1),
            queue.update_task(task.task_id, progress=2),
            queue.update_task(task.task_id, progress=3),
        )

        # Final progress should be one of the values (3 is most likely)
        final_task = queue.get_task(task.task_id)
        assert final_task.progress in [1, 2, 3]


class TestTaskStatusEnum:
    """Test TaskStatus enum."""

    def test_task_status_values(self):
        """Test TaskStatus enum has expected values."""
        assert TaskStatus.QUEUED == "queued"
        assert TaskStatus.PROCESSING == "processing"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_task_status_comparison(self):
        """Test TaskStatus can be compared."""
        assert TaskStatus.QUEUED == TaskStatus.QUEUED
        assert TaskStatus.QUEUED != TaskStatus.PROCESSING
