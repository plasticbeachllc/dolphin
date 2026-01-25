import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.ingest.branch_tracker import BranchState, detect_branch_switch, get_current_branch_state


class TestBranchTracker:
    @patch("subprocess.check_output")
    def test_get_current_branch_state_success(self, mock_check_output):
        # Setup mocks
        mock_check_output.side_effect = [
            b"1234567890abcdef\n",  # commit sha
            b"main\n",  # branch name
        ]

        # Test
        state = get_current_branch_state(Path("/tmp/repo"))

        # Verify
        assert state.commit_sha == "1234567890abcdef"
        assert state.branch == "main"
        assert mock_check_output.call_count == 2

    @patch("subprocess.check_output")
    def test_get_current_branch_state_failure(self, mock_check_output):
        # Setup mocks to raise error
        mock_check_output.side_effect = subprocess.CalledProcessError(1, ["git"], output=b"fatal: not a git repo")

        # Test
        with pytest.raises(RuntimeError, match="Failed to get git state"):
            get_current_branch_state(Path("/tmp/repo"))

    def test_detect_branch_switch_true(self):
        old_state = BranchState(branch="main", commit_sha="123")
        new_state = BranchState(branch="feature", commit_sha="456")

        assert detect_branch_switch(old_state, new_state) is True

    def test_detect_branch_switch_false_same_branch(self):
        old_state = BranchState(branch="main", commit_sha="123")
        new_state = BranchState(branch="main", commit_sha="456")

        assert detect_branch_switch(old_state, new_state) is False

    def test_detect_branch_switch_false_detached(self):
        # Switching from/to detached HEAD often shows up as "HEAD" or specific SHA in some git versions,
        # but our logic specifically checks if branch names differ.
        # If we are in detached HEAD, branch might be "HEAD"
        old_state = BranchState(branch="HEAD", commit_sha="123")
        new_state = BranchState(branch="HEAD", commit_sha="456")

        assert detect_branch_switch(old_state, new_state) is False
