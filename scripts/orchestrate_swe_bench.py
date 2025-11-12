#!/usr/bin/env python3
"""Orchestration script for SWE-Bench Lite evaluation.

Handles:
- Downloading repos at specific commits
- Indexing with appropriate embedding models (small/large)
- Tracking indexed state
- Running file identification evaluation
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SWEBenchOrchestrator:
    """Orchestrates SWE-Bench Lite evaluation workflow."""

    def __init__(
        self,
        repos_dir: Path,
        index_dir: Path,
        config_path: Path,
        state_file: Path
    ):
        self.repos_dir = repos_dir
        self.index_dir = index_dir
        self.config_path = config_path
        self.state_file = state_file

        # Load configuration
        with open(config_path) as f:
            self.config = json.load(f)

        # Load or initialize state
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        """Load orchestration state."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return {
            "repos_cloned": {},
            "repos_indexed": {},
            "commits_indexed": {},
            "last_updated": None
        }

    def _save_state(self):
        """Save orchestration state."""
        import time
        self.state["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def clone_repo(self, repo_name: str) -> bool:
        """Clone repository if not already present."""
        repo_path = self.repos_dir / repo_name.replace("/", "__")

        if repo_path.exists():
            print(f"  ✓ Already cloned: {repo_name}")
            return True

        print(f"  Cloning {repo_name}...")

        try:
            # Clone with depth 1 to save space, then fetch full history
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    f"https://github.com/{repo_name}.git",
                    str(repo_path)
                ],
                capture_output=True,
                text=True,
                timeout=600  # 10 min timeout
            )

            if result.returncode != 0:
                print(f"  ✗ Clone failed: {result.stderr}")
                return False

            self.state["repos_cloned"][repo_name] = str(repo_path)
            self._save_state()
            print(f"  ✓ Cloned to: {repo_path}")
            return True

        except Exception as e:
            print(f"  ✗ Clone error: {e}")
            return False

    def checkout_commit(self, repo_name: str, commit_sha: str) -> bool:
        """Checkout specific commit in repository."""
        repo_path = self.repos_dir / repo_name.replace("/", "__")

        if not repo_path.exists():
            print(f"  ✗ Repo not cloned: {repo_name}")
            return False

        try:
            # Fetch commit if needed
            subprocess.run(
                ["git", "fetch", "origin", commit_sha],
                cwd=repo_path,
                capture_output=True,
                timeout=300
            )

            # Checkout
            result = subprocess.run(
                ["git", "checkout", commit_sha],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"  ✗ Checkout failed: {result.stderr}")
                return False

            return True

        except Exception as e:
            print(f"  ✗ Checkout error: {e}")
            return False

    def index_repo(self, repo_name: str, embed_model: str = "small") -> bool:
        """Index repository with specified embedding model."""
        repo_path = self.repos_dir / repo_name.replace("/", "__")

        if not repo_path.exists():
            print(f"  ✗ Repo not found: {repo_path}")
            return False

        # Check if already indexed
        index_key = f"{repo_name}:{embed_model}"
        if index_key in self.state["repos_indexed"]:
            print(f"  ✓ Already indexed with {embed_model} model: {repo_name}")
            return True

        print(f"  Indexing {repo_name} with {embed_model} model...")

        try:
            # Run indexing command
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "kb.cli",
                    "index",
                    str(repo_path),
                    "--embed-model",
                    embed_model
                ],
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                print(f"  ✗ Indexing failed: {result.stderr}")
                return False

            self.state["repos_indexed"][index_key] = {
                "repo_path": str(repo_path),
                "embed_model": embed_model,
                "indexed_at": subprocess.run(
                    ["date", "+%Y-%m-%d %H:%M:%S"],
                    capture_output=True,
                    text=True
                ).stdout.strip()
            }
            self._save_state()

            print(f"  ✓ Indexed successfully")
            return True

        except Exception as e:
            print(f"  ✗ Indexing error: {e}")
            return False

    def setup_all_repos(self):
        """Clone and index all configured repos."""
        print("="*80)
        print("SWE-BENCH LITE REPO SETUP")
        print("="*80)

        repos = self.config["repos"]
        total = len(repos)

        for i, (repo_name, repo_config) in enumerate(repos.items(), 1):
            print(f"\n[{i}/{total}] {repo_name}")
            print(f"  Size: {repo_config['size_category']}")
            print(f"  Model: {repo_config['embed_model']}")
            print(f"  Instances: {repo_config['instances']}")

            # Clone
            if not self.clone_repo(repo_name):
                print(f"  ⚠️  Skipping index due to clone failure")
                continue

            # Index with configured model
            embed_model = repo_config["embed_model"]
            if not self.index_repo(repo_name, embed_model):
                print(f"  ⚠️  Index failed, continuing anyway")

        print("\n" + "="*80)
        print("SETUP COMPLETE")
        print("="*80)
        self._print_status()

    def _print_status(self):
        """Print current setup status."""
        repos = self.config["repos"]
        cloned_count = sum(
            1 for repo in repos
            if repo in self.state["repos_cloned"]
        )
        indexed_count = len(self.state["repos_indexed"])

        print(f"\nStatus:")
        print(f"  Repos cloned: {cloned_count}/{len(repos)}")
        print(f"  Repos indexed: {indexed_count} (small + large model)")

        # Storage estimate
        repos_dir_size = self._get_dir_size(self.repos_dir)
        index_dir_size = self._get_dir_size(self.index_dir)

        print(f"\nStorage:")
        print(f"  Source code: {repos_dir_size / 1024:.1f} GB")
        print(f"  Indices: {index_dir_size / 1024:.1f} GB")
        print(f"  Total: {(repos_dir_size + index_dir_size) / 1024:.1f} GB")

    def _get_dir_size(self, path: Path) -> float:
        """Get directory size in MB."""
        if not path.exists():
            return 0.0

        try:
            result = subprocess.run(
                ["du", "-sm", str(path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return float(result.stdout.split()[0])
        except:
            pass
        return 0.0

    def list_status(self):
        """List current status of all repos."""
        print("="*80)
        print("SWE-BENCH REPOS STATUS")
        print("="*80)

        repos = self.config["repos"]
        for repo_name, repo_config in repos.items():
            cloned = repo_name in self.state["repos_cloned"]
            indexed_small = f"{repo_name}:small" in self.state["repos_indexed"]
            indexed_large = f"{repo_name}:large" in self.state["repos_indexed"]

            status_parts = []
            if cloned:
                status_parts.append("✓ cloned")
            if indexed_small:
                status_parts.append("✓ indexed(small)")
            if indexed_large:
                status_parts.append("✓ indexed(large)")

            status = ", ".join(status_parts) if status_parts else "✗ not setup"

            print(f"\n{repo_name}")
            print(f"  Model: {repo_config['embed_model']}")
            print(f"  Status: {status}")

        print("\n" + "="*80)
        self._print_status()


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate SWE-Bench Lite evaluation setup"
    )

    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path("test-repos/swe-bench"),
        help="Directory for cloned repos"
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path.home() / ".dolphin" / "knowledge_store",
        help="Directory for vector indices"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("test-data/swe_bench_repos.json"),
        help="Repo configuration file"
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("test-data/swe_bench_state.json"),
        help="State tracking file"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Setup command
    subparsers.add_parser("setup", help="Clone and index all repos")

    # Status command
    subparsers.add_parser("status", help="Show current setup status")

    # Clone command
    clone_parser = subparsers.add_parser("clone", help="Clone specific repo")
    clone_parser.add_argument("repo", help="Repo name (e.g., django/django)")

    # Index command
    index_parser = subparsers.add_parser("index", help="Index specific repo")
    index_parser.add_argument("repo", help="Repo name")
    index_parser.add_argument(
        "--model",
        choices=["small", "large"],
        default="small",
        help="Embedding model"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize orchestrator
    orchestrator = SWEBenchOrchestrator(
        repos_dir=args.repos_dir,
        index_dir=args.index_dir,
        config_path=args.config,
        state_file=args.state_file
    )

    # Execute command
    if args.command == "setup":
        orchestrator.setup_all_repos()
    elif args.command == "status":
        orchestrator.list_status()
    elif args.command == "clone":
        orchestrator.clone_repo(args.repo)
    elif args.command == "index":
        orchestrator.index_repo(args.repo, args.model)


if __name__ == "__main__":
    main()
