import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from watchfiles import Change

from kb.config import KBConfig
from kb.ingest.branch_tracker import BranchState
from kb.ingest.watcher import RepoWatcher


@pytest.mark.asyncio
class TestRepoWatcher:
    @pytest.fixture
    def mock_pipeline(self):
        pipeline = MagicMock()
        pipeline.metadata.get_repo_by_name.return_value = {
            "id": 1,
            "root_path": "/tmp/repo",
            "default_embed_model": "large",
        }
        pipeline.metadata.get_pending_changes.return_value = []
        return pipeline

    @pytest.fixture
    def config(self):
        return KBConfig()

    @patch("kb.ingest.watcher.get_current_branch_state")
    @patch("kb.ignores.build_ignore_pathspec")
    async def test_init(self, mock_build_ignore, mock_get_branch, mock_pipeline, config):
        from pathspec import PathSpec

        mock_build_ignore.return_value = PathSpec.from_lines("gitignore", [])
        mock_get_branch.return_value = BranchState(branch="main", commit_sha="123")

        watcher = RepoWatcher("repo", config, mock_pipeline)
        assert watcher.repo_id == 1
        assert str(watcher.root) == "/tmp/repo"
        assert watcher.current_branch_state is not None
        assert watcher.current_branch_state.branch == "main"

    @patch("kb.ingest.watcher.get_current_branch_state")
    @patch("kb.ignores.build_ignore_pathspec")
    async def test_filter_changes(self, mock_build_ignore, mock_get_branch, mock_pipeline, config):
        from pathspec import PathSpec

        mock_build_ignore.return_value = PathSpec.from_lines("gitignore", [])
        mock_get_branch.return_value = BranchState(branch="main", commit_sha="123")

        watcher = RepoWatcher("repo", config, mock_pipeline)

        # Set up manual ignore for testing
        watcher.ignore_spec = MagicMock()
        watcher.ignore_spec.match_file.side_effect = lambda x: x.endswith(".ignored")

        changes = {
            (Change.modified, "/tmp/repo/file.py"),
            (Change.added, "/tmp/repo/test.ignored"),
            (Change.modified, "/tmp/repo/.git/HEAD"),
        }

        filtered = watcher._filter_changes(changes)

        # Expected: file.py only
        # .git should be filtered by code logic
        # .ignored should be filtered by ignore_spec

        assert len(filtered) == 1
        assert filtered[0][1] == "file.py"

    @patch("kb.ingest.watcher.get_current_branch_state")
    @patch("kb.ignores.build_ignore_pathspec")
    async def test_check_branch_switch_no_change(self, mock_build_ignore, mock_get_branch, mock_pipeline, config):
        from pathspec import PathSpec

        mock_build_ignore.return_value = PathSpec.from_lines("gitignore", [])
        mock_get_branch.return_value = BranchState(branch="main", commit_sha="123")

        watcher = RepoWatcher("repo", config, mock_pipeline)

        # Mock executor to run synchronously or return value immediately
        # But _check_branch_switch uses await loop.run_in_executor
        # We can patch loop.run_in_executor

        with patch.object(asyncio.get_event_loop(), "run_in_executor", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = BranchState(branch="main", commit_sha="456")  # Same branch, new commit

            await watcher._check_branch_switch()

            # Should NOT trigger reconcile
            mock_pipeline.reconcile_branch_switch.assert_not_called()
            # Should update state
            assert watcher.current_branch_state is not None
            assert watcher.current_branch_state.commit_sha == "456"

    @patch("kb.ingest.watcher.get_current_branch_state")
    @patch("kb.ignores.build_ignore_pathspec")
    async def test_check_branch_switch_detected(self, mock_build_ignore, mock_get_branch, mock_pipeline, config):
        from pathspec import PathSpec

        mock_build_ignore.return_value = PathSpec.from_lines("gitignore", [])
        initial_state = BranchState(branch="main", commit_sha="123")
        mock_get_branch.return_value = initial_state

        watcher = RepoWatcher("repo", config, mock_pipeline)

        new_state = BranchState(branch="feature", commit_sha="456")

        with patch.object(asyncio.get_event_loop(), "run_in_executor", new_callable=AsyncMock) as mock_run:
            # First call returns new state (get_current_branch_state)
            # Second call (reconcile) returns None
            def side_effect(executor, func, *args):
                if func == mock_pipeline.reconcile_branch_switch:
                    return None
                return new_state

            mock_run.side_effect = side_effect

            await watcher._check_branch_switch()

            # Should trigger reconcile
            # Since we mocked run_in_executor, we verify it was called with reconcile_branch_switch
            calls = mock_run.call_args_list
            reconcile_called = any(call[0][1] == mock_pipeline.reconcile_branch_switch for call in calls)
            assert reconcile_called

    @patch("kb.ingest.watcher.get_current_branch_state")
    @patch("kb.ignores.build_ignore_pathspec")
    async def test_record_changes(self, mock_build_ignore, mock_get_branch, mock_pipeline, config, tmp_path):
        from pathspec import PathSpec

        mock_build_ignore.return_value = PathSpec.from_lines("gitignore", [])
        mock_get_branch.return_value = BranchState(branch="main", commit_sha="123")

        watcher = RepoWatcher("repo", config, mock_pipeline)
        watcher.root = tmp_path
        (tmp_path / "file.py").write_text("print('ok')")

        # Mock DB connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pipeline.metadata._connect.return_value.__enter__.return_value = mock_conn

        # Mock fetchone to return None (no existing pending change)
        mock_cursor.fetchone.return_value = None

        changes = [(Change.modified, "file.py")]

        # We need to run the protected method which runs in executor.
        # For unit test, we can call the inner function directly or mock executor.
        # But _record_changes defines an inner function _db_op.
        # It's easier to mock the run_in_executor to execute the function immediately.

        with patch.object(asyncio.get_event_loop(), "run_in_executor", new_callable=AsyncMock) as mock_run:
            # We want to execute the function passed to run_in_executor
            async def side_effect(executor, func, *args):
                return func(*args)

            mock_run.side_effect = side_effect

            await watcher._record_changes(changes)

            # Verify DB inserts
            assert mock_cursor.execute.call_count >= 2  # Select check + Insert
            # Check insert args
            insert_call = mock_cursor.execute.call_args_list[-1]
            assert "INSERT INTO pending_changes" in insert_call[0][0]
            assert insert_call[0][1][1] == "file.py"
            assert insert_call[0][1][2] == "modified"

    @patch("kb.ingest.watcher.get_current_branch_state")
    @patch("kb.ignores.build_ignore_pathspec")
    async def test_process_pending_sync(self, mock_build_ignore, mock_get_branch, mock_pipeline, config):
        from pathspec import PathSpec

        mock_build_ignore.return_value = PathSpec.from_lines("gitignore", [])
        mock_get_branch.return_value = BranchState(branch="main", commit_sha="123")

        watcher = RepoWatcher("repo", config, mock_pipeline)

        # Mock pending changes
        mock_pipeline.metadata.get_pending_changes.return_value = [
            {"id": 1, "repo_id": 1, "file_path": "file.py", "change_type": "modified", "detected_at": "now"},
            {"id": 2, "repo_id": 1, "file_path": "deleted.py", "change_type": "deleted", "detected_at": "now"},
        ]

        mock_pipeline.metadata.begin_session.return_value = 999

        # Run sync method directly (simulating executor)
        watcher._process_pending_sync()

        # Verify pipeline calls
        mock_pipeline.process_files.assert_called_once()
        call_args = mock_pipeline.process_files.call_args[1]
        assert call_args["files"] == ["file.py"]
        assert call_args["session_id"] == 999

        mock_pipeline.process_deletions.assert_called_once()
        del_args = mock_pipeline.process_deletions.call_args[1]
        assert del_args["files"] == ["deleted.py"]

        # Verify metadata updates
        mock_pipeline.metadata.mark_changes_processed.assert_called_once_with([1, 2])
        mock_pipeline.metadata.set_session_status.assert_called_once_with(999, "succeeded")
