from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from ..config import KBConfig
from ..store import LanceDBStore, SQLiteMetadataStore
from ..ingest.scanner import FileCandidate, scan_repo
from ..ignores import build_ignore_set


@dataclass
class IngestionPipeline:
    """Coordinates scanning, chunking, and persistence."""

    config: KBConfig
    lancedb: LanceDBStore
    metadata: SQLiteMetadataStore

    def _git(self, root: Path, *args: str) -> str:
        try:
            out = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)
            return out.decode("utf-8")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.output.decode("utf-8", errors="ignore"))

    def _ensure_clean_working_tree(self, root: Path) -> None:
        # only consider tracked files
        try:
            subprocess.check_call(["git", "-C", str(root), "update-index", "-q", "--refresh"])
            subprocess.check_call(["git", "-C", str(root), "diff-index", "--quiet", "HEAD", "--"])
        except subprocess.CalledProcessError:
            raise RuntimeError("Working tree has tracked changes; commit or stash before indexing.")

    def scan(self, repo_name: str, *, dry_run: bool = False, force: bool = False) -> dict:
        """Perform scanning for the named repository and persist file catalog.

        Returns a summary dictionary with counts and session info.
        """
        repo = self.metadata.get_repo_by_name(repo_name)
        if not repo:
            raise ValueError(f"Repository not registered: {repo_name}")

        repo_id = int(repo["id"])
        root = Path(repo["root_path"])
        embed_model = repo.get("default_embed_model", self.config.default_embed_model)

        # Ensure clean working tree and capture provenance (unless forced)
        if not force:
            self._ensure_clean_working_tree(root)
        else:
            print(f"Warning: force=True, skipping clean working tree check for {repo_name}")
        commit_sha = self._git(root, "rev-parse", "HEAD").strip()
        branch = self._git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()

        # Start session
        session_id = self.metadata.begin_session(repo_id, commit_sha, branch, embed_model)

        # Build ignore set (merge config + security patterns)
        extra_security = {
            "**/id_rsa",
            "**/*.pem",
            "**/.aws/**",
            "**/gcloud/**",
            "**/secrets/**",
            "**/*keys.json",
            "**/*service_account.json",
            "**/*auth.json",
        }
        merged_ignores = set(self.config.ignore) | extra_security

        # Scan
        candidates: List[FileCandidate] = scan_repo(root, merged_ignores)

        summary = {
            "repo": repo_name,
            "repo_id": repo_id,
            "session_id": session_id,
            "commit": commit_sha,
            "branch": branch,
            "files_tracked": None,
            "files_kept": len(candidates),
        }

        # Persist file catalog unless dry_run
        if not dry_run:
            for c in candidates:
                self.metadata.upsert_file(
                    repo_id,
                    path=c.rel_path,
                    ext=c.ext,
                    language=c.language,
                    is_binary=c.is_binary,
                    size_bytes=c.size_bytes,
                )
            self.metadata.bump_session_counters(session_id, files_indexed=len(candidates))
            # Leave session running if next phases will proceed; here we mark succeeded for scan-only
            self.metadata.set_session_status(session_id, "succeeded")
        else:
            # Dry run: leave session as running but record file count
            self.metadata.bump_session_counters(session_id, files_indexed=len(candidates))

        summary["files_kept"] = len(candidates)
        return summary

    def run(self, repo_name: str, repo_path: Path, *, dry_run: bool = False) -> None:
        """Compatibility wrapper: call scan and print a summary."""
        _ = repo_path
        result = self.scan(repo_name, dry_run=dry_run)
        print(f"Scan complete for {repo_name}: files_kept={result['files_kept']}, session={result['session_id']}")
