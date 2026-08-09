"""Tests for bounded, non-mutating child repository discovery."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kb.ingest.scanner import scan_repo
from kb.services import repository_boundaries as boundary_module, worktree as worktree_module
from kb.services.repository_boundaries import (
    RepositoryBoundaryError,
    RepositoryBoundaryKind,
    RepositoryBoundaryState,
    path_is_within_boundary,
    plan_parent_scan,
    validate_parent_scan,
)
from kb.services.worktree import discover_git_worktree_sync


def test_nested_repository_is_enrollable_and_excluded_from_parent_scan(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    child = _commit_repository(parent / "nested repository", "child.py")

    plan = plan_parent_scan(discover_git_worktree_sync(parent))

    assert plan.excluded_subtrees == frozenset({"nested repository"})
    assert len(plan.repository_boundaries) == 1
    boundary = plan.repository_boundaries[0]
    assert boundary.kind is RepositoryBoundaryKind.NESTED_GIT
    assert boundary.state is RepositoryBoundaryState.ENROLLABLE
    assert boundary.root == child
    assert boundary.observed_commit == _git(child, "rev-parse", "HEAD")
    assert {candidate.rel_path for candidate in scan_repo(parent, [])} == {"parent.py"}


def test_initialized_submodule_is_classified_from_gitlink_without_recursive_submodule_command(tmp_path: Path) -> None:
    source = _commit_repository(tmp_path / "source", "source.py")
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    _git(parent, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(source), "vendor/child")
    _git(parent, "commit", "-qm", "Add child")

    plan = plan_parent_scan(discover_git_worktree_sync(parent))

    assert len(plan.repository_boundaries) == 1
    boundary = plan.repository_boundaries[0]
    assert boundary.kind is RepositoryBoundaryKind.SUBMODULE
    assert boundary.state is RepositoryBoundaryState.ENROLLABLE
    assert boundary.relative_path == "vendor/child"
    assert boundary.root == parent / "vendor" / "child"
    assert boundary.expected_commit == _git(source, "rev-parse", "HEAD")
    assert boundary.observed_commit == boundary.expected_commit
    assert {candidate.rel_path for candidate in scan_repo(parent, [])} == {".gitmodules", "parent.py"}


def test_deinitialized_and_missing_submodules_remain_hard_boundaries(tmp_path: Path) -> None:
    source = _commit_repository(tmp_path / "source", "source.py")
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    _git(parent, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(source), "child")
    _git(parent, "commit", "-qm", "Add child")
    _git(parent, "submodule", "deinit", "-f", "--", "child")

    uninitialized = plan_parent_scan(discover_git_worktree_sync(parent)).repository_boundaries[0]
    assert uninitialized.state is RepositoryBoundaryState.UNINITIALIZED

    (parent / "child").rmdir()
    missing = plan_parent_scan(discover_git_worktree_sync(parent)).repository_boundaries[0]
    assert missing.state is RepositoryBoundaryState.MISSING
    assert missing.relative_path == "child"


def test_symlink_git_marker_is_invalid_and_still_excludes_the_subtree(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    child = parent / "fixture"
    child.mkdir()
    (child / "secret.py").write_text("SECRET = True\n")
    (child / ".git").symlink_to(parent / ".git", target_is_directory=True)

    plan = plan_parent_scan(discover_git_worktree_sync(parent))

    assert plan.excluded_subtrees == frozenset({"fixture"})
    assert plan.repository_boundaries[0].state is RepositoryBoundaryState.INVALID
    assert not any(candidate.rel_path == "fixture/secret.py" for candidate in scan_repo(parent, []))


def test_escaping_git_file_is_invalid_without_following_the_external_repository(tmp_path: Path) -> None:
    outside = _commit_repository(tmp_path / "outside", "outside.py")
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    child = parent / "malicious"
    child.mkdir()
    (child / ".git").write_text(f"gitdir: {outside / '.git'}\n")

    plan = plan_parent_scan(discover_git_worktree_sync(parent))

    boundary = plan.repository_boundaries[0]
    assert boundary.relative_path == "malicious"
    assert boundary.state is RepositoryBoundaryState.INVALID
    assert boundary.root is None


def test_marker_walk_stops_at_the_first_nested_repository(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    child = _commit_repository(parent / "child", "child.py")
    _commit_repository(child / "grandchild", "grandchild.py")

    plan = plan_parent_scan(discover_git_worktree_sync(parent))

    assert [boundary.relative_path for boundary in plan.repository_boundaries] == ["child"]


def test_nested_linked_worktree_is_a_distinct_boundary_in_the_same_repository_family(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    linked = parent / "linked"
    _git(parent, "worktree", "add", "-q", "-b", "linked-branch", str(linked))

    parent_worktree = discover_git_worktree_sync(parent)
    linked_worktree = discover_git_worktree_sync(linked)
    plan = plan_parent_scan(parent_worktree)

    boundary = plan.repository_boundaries[0]
    assert boundary.kind is RepositoryBoundaryKind.NESTED_GIT
    assert boundary.state is RepositoryBoundaryState.ENROLLABLE
    assert boundary.root == linked
    assert linked_worktree.common_git_dir_identity == parent_worktree.common_git_dir_identity
    assert linked_worktree.worktree_git_dir_identity != parent_worktree.worktree_git_dir_identity


def test_conflicted_gitlink_is_authoritative_and_never_probed_as_nested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    child = parent / "child"
    child.mkdir()
    (child / ".git").mkdir()
    object_id = "a" * 40
    output = "\0".join(
        (
            f"160000 {object_id} 1\tchild",
            f"160000 {'b' * 40} 2\tchild",
            "",
        )
    )
    monkeypatch.setattr(
        boundary_module,
        "run_git_read_only",
        lambda *_args: subprocess.CompletedProcess([], 0, output, ""),
    )

    plan = plan_parent_scan(discover_git_worktree_sync(parent))

    assert len(plan.repository_boundaries) == 1
    assert plan.repository_boundaries[0].kind is RepositoryBoundaryKind.SUBMODULE
    assert plan.repository_boundaries[0].state is RepositoryBoundaryState.CONFLICTED
    assert plan.excluded_subtrees == frozenset({"child"})


def test_discovery_runs_only_bounded_read_only_git_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = _commit_repository(tmp_path / "source", "source.py")
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    _git(parent, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(source), "child")
    _git(parent, "commit", "-qm", "Add child")
    commands: list[tuple[str, ...]] = []
    original_run_git = worktree_module._run_git

    def observe(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        return original_run_git(path, *arguments)

    monkeypatch.setattr(worktree_module, "_run_git", observe)

    plan_parent_scan(discover_git_worktree_sync(parent))

    assert commands
    assert {arguments[0] for arguments in commands} <= {"ls-files", "rev-parse"}


def test_boundary_walk_limit_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    (parent / "one").mkdir()
    monkeypatch.setattr(boundary_module, "_MAX_WALKED_ENTRIES", 1)

    with pytest.raises(RepositoryBoundaryError, match="BOUNDARY_WALK_LIMIT_EXCEEDED"):
        plan_parent_scan(discover_git_worktree_sync(parent))


def test_validation_rejects_a_boundary_created_after_planning(tmp_path: Path) -> None:
    parent = _commit_repository(tmp_path / "parent", "parent.py")
    plan = plan_parent_scan(discover_git_worktree_sync(parent))
    _commit_repository(parent / "late-child", "child.py")

    with pytest.raises(RepositoryBoundaryError, match="BOUNDARY_SNAPSHOT_CHANGED"):
        validate_parent_scan(plan)


def test_boundary_prefix_matching_does_not_mask_similar_siblings() -> None:
    boundaries = frozenset({"vendor/sub"})

    assert path_is_within_boundary("vendor/sub", boundaries)
    assert path_is_within_boundary("vendor/sub/file.py", boundaries)
    assert not path_is_within_boundary("vendor/submarine.py", boundaries)


def _commit_repository(path: Path, filename: str) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "dolphin-tests@example.invalid")
    _git(path, "config", "user.name", "Dolphin Tests")
    (path / filename).write_text(f"# {filename}\n")
    _git(path, "add", "-f", filename)
    _git(path, "commit", "-qm", f"Add {filename}")
    return path


def _git(path: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
