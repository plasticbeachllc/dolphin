"""Tests for GraphCacheValidator."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from kb.graph_intelligence.cache_validator import GraphCacheValidator


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return Mock()


@pytest.fixture
def validator(mock_db):
    """Create a GraphCacheValidator instance."""
    return GraphCacheValidator(db=mock_db, repo_id=1, edge_change_threshold=5, ttl_minutes=10)


class TestCacheValidation:
    """Test cache validation logic."""

    def test_no_cache_state_invalid(self, validator, mock_db):
        """Test that missing cache state invalidates cache."""
        # Mock database to return no cache state
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst
            mock_session_inst.exec.return_value.first.return_value = None

            assert not validator.is_cache_valid()

    def test_commit_sha_mismatch_invalid(self, validator, mock_db):
        """Test that commit SHA mismatch invalidates cache."""
        # Mock cache state with old commit
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock cache state
            cache_state = Mock()
            cache_state.commit_sha = "old_commit_123"
            cache_state.last_rebuild_at = datetime.now().isoformat()
            cache_state.edge_changes_since_rebuild = 0
            mock_session_inst.exec.return_value.first.return_value = cache_state

            # Mock git command to return different commit
            with patch.object(validator, "_get_current_commit_sha", return_value="new_commit_456"):
                assert not validator.is_cache_valid()

    def test_edge_threshold_exceeded_invalid(self, validator, mock_db):
        """Test that exceeding edge threshold invalidates cache."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock cache state with many edge changes
            cache_state = Mock()
            cache_state.commit_sha = "commit_123"
            cache_state.last_rebuild_at = datetime.now().isoformat()
            cache_state.edge_changes_since_rebuild = 10  # Exceeds threshold of 5
            mock_session_inst.exec.return_value.first.return_value = cache_state

            # Mock same commit
            with patch.object(validator, "_get_current_commit_sha", return_value="commit_123"):
                assert not validator.is_cache_valid()

    def test_ttl_exceeded_invalid(self, validator, mock_db):
        """Test that exceeding TTL invalidates cache."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock cache state with old timestamp
            old_time = datetime.now() - timedelta(minutes=15)  # Exceeds 10 minute TTL
            cache_state = Mock()
            cache_state.commit_sha = "commit_123"
            cache_state.last_rebuild_at = old_time.isoformat()
            cache_state.edge_changes_since_rebuild = 0
            mock_session_inst.exec.return_value.first.return_value = cache_state

            # Mock same commit
            with patch.object(validator, "_get_current_commit_sha", return_value="commit_123"):
                assert not validator.is_cache_valid()

    def test_valid_cache(self, validator, mock_db):
        """Test that valid cache passes all checks."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock cache state with current values
            cache_state = Mock()
            cache_state.commit_sha = "commit_123"
            cache_state.last_rebuild_at = datetime.now().isoformat()
            cache_state.edge_changes_since_rebuild = 2  # Below threshold of 5
            cache_state.node_count = 100
            cache_state.edge_count = 50
            mock_session_inst.exec.return_value.first.return_value = cache_state

            # Mock same commit
            with patch.object(validator, "_get_current_commit_sha", return_value="commit_123"):
                assert validator.is_cache_valid()


class TestGitSHATracking:
    """Test git SHA tracking functionality."""

    def test_get_commit_sha_success(self, validator, mock_db):
        """Test successful git SHA retrieval."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock repo
            repo = Mock()
            repo.root_path = "/tmp/test_repo"
            mock_session_inst.exec.return_value.first.return_value = repo

            # Mock git command
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="abc123def456\n", stderr="")

                # Mock Path.exists
                with patch.object(Path, "exists", return_value=True):
                    commit_sha = validator._get_current_commit_sha()
                    assert commit_sha == "abc123def456"

    def test_get_commit_sha_not_git_repo(self, validator, mock_db):
        """Test handling of non-git repository."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock repo
            repo = Mock()
            repo.root_path = "/tmp/not_a_repo"
            mock_session_inst.exec.return_value.first.return_value = repo

            # Mock .git dir doesn't exist
            with patch.object(Path, "exists", return_value=False):
                commit_sha = validator._get_current_commit_sha()
                assert commit_sha is None

    def test_get_commit_sha_git_command_failed(self, validator, mock_db):
        """Test handling of git command failure."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock repo
            repo = Mock()
            repo.root_path = "/tmp/test_repo"
            mock_session_inst.exec.return_value.first.return_value = repo

            # Mock git command failure
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=1, stdout="", stderr="fatal: not a git repository")

                with patch.object(Path, "exists", return_value=True):
                    commit_sha = validator._get_current_commit_sha()
                    assert commit_sha is None


class TestCacheStateManagement:
    """Test cache state update operations."""

    def test_update_cache_state_new(self, validator, mock_db):
        """Test creating new cache state."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # No existing cache state
            mock_session_inst.exec.return_value.first.return_value = None

            validator.update_cache_state(commit_sha="abc123", node_count=100, edge_count=50)

            # Verify session.add was called
            assert mock_session_inst.add.called

    def test_update_cache_state_existing(self, validator, mock_db):
        """Test updating existing cache state."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock existing cache state
            cache_state = Mock()
            cache_state.commit_sha = "old_commit"
            cache_state.edge_changes_since_rebuild = 50
            mock_session_inst.exec.return_value.first.return_value = cache_state

            validator.update_cache_state(commit_sha="new_commit", node_count=200, edge_count=100)

            # Verify cache state was updated
            assert cache_state.commit_sha == "new_commit"
            assert cache_state.node_count == 200
            assert cache_state.edge_count == 100
            assert cache_state.edge_changes_since_rebuild == 0

    def test_increment_edge_changes(self, validator, mock_db):
        """Test incrementing edge change counter."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock existing cache state
            cache_state = Mock()
            cache_state.edge_changes_since_rebuild = 10
            mock_session_inst.exec.return_value.first.return_value = cache_state

            validator.increment_edge_changes(5)

            # Verify counter was incremented
            assert cache_state.edge_changes_since_rebuild == 15


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_timestamp_format(self, validator, mock_db):
        """Test handling of invalid timestamp in cache state."""
        with patch("kb.graph_intelligence.cache_validator.Session") as mock_session:
            mock_session_inst = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_session_inst

            # Mock cache state with invalid timestamp
            cache_state = Mock()
            cache_state.commit_sha = "commit_123"
            cache_state.last_rebuild_at = "invalid_timestamp"
            cache_state.edge_changes_since_rebuild = 0
            mock_session_inst.exec.return_value.first.return_value = cache_state

            # Mock same commit
            with patch.object(validator, "_get_current_commit_sha", return_value="commit_123"):
                # Should return False due to timestamp parse error
                assert not validator.is_cache_valid()

    def test_custom_thresholds(self, mock_db):
        """Test custom edge threshold and TTL values."""
        custom_validator = GraphCacheValidator(
            db=mock_db,
            repo_id=1,
            edge_change_threshold=500,
            ttl_minutes=1440,  # 24 hours in minutes
        )

        assert custom_validator.edge_change_threshold == 500
        assert custom_validator.ttl == timedelta(minutes=1440)
