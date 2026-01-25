"""Module for tracking git branch state to detect switches."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BranchState:
    """Represents the state of a git branch at a specific time."""

    branch: str
    commit_sha: str


def get_current_branch_state(repo_root: Path) -> BranchState:
    """Get the current branch and commit SHA for a repository.

    Args:
        repo_root: Root path of the git repository

    Returns:
        BranchState object with current branch and commit
    """
    try:
        commit_sha = (
            subprocess.check_output(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"], stderr=subprocess.STDOUT
            )
            .decode("utf-8")
            .strip()
        )
        branch = (
            subprocess.check_output(
                ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.STDOUT,
            )
            .decode("utf-8")
            .strip()
        )
        return BranchState(branch=branch, commit_sha=commit_sha)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get git state: {e.output.decode('utf-8', errors='ignore')}")


def detect_branch_switch(old_state: BranchState | None, new_state: BranchState) -> bool:
    """Detect if a branch switch has occurred.

    Args:
        old_state: Previous branch state (from last indexing)
        new_state: Current branch state

    Returns:
        True if branch name has changed
    """
    if old_state is None:
        return False

    return old_state.branch != new_state.branch
