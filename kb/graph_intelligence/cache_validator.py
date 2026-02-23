"""Cache validation for NetworkX graph management."""

import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from kb.store.sql_models import GraphCacheState, Repo

logger = logging.getLogger(__name__)


class GraphCacheValidator:
    """Validates whether cached NetworkX graph is still current."""

    def __init__(self, db, repo_id: int, edge_change_threshold: int = 5, ttl_minutes: int = 10):
        """Initialize cache validator.

        Args:
            db: Database connection
            repo_id: Repository ID
            edge_change_threshold: Max edge changes before invalidation (default: 5)
            ttl_minutes: Cache TTL in minutes (default: 10)
        """
        self.db = db
        self.repo_id = repo_id
        self.edge_change_threshold = edge_change_threshold
        self.ttl = timedelta(minutes=ttl_minutes)

    def is_cache_valid(self) -> bool:
        """Check if cached NetworkX graph is still valid.

        Returns:
            True if cache is valid, False if rebuild needed
        """
        # Get cache state
        cache_state = self._get_cache_state()
        if not cache_state:
            logger.info(f"Cache invalid for repo {self.repo_id}: no cache state")
            return False

        # Check 1: Commit SHA match
        current_commit = self._get_current_commit_sha()
        if current_commit and cache_state["commit_sha"] != current_commit:
            logger.info(
                f"Cache invalid for repo {self.repo_id}: commit changed "
                f"{cache_state['commit_sha'][:7]} → {current_commit[:7]}"
            )
            return False

        # Check 2: Edge change threshold
        edge_changes = cache_state.get("edge_changes_since_rebuild", 0)
        if edge_changes > self.edge_change_threshold:
            logger.info(
                f"Cache invalid for repo {self.repo_id}: "
                f"{edge_changes} edge changes exceed threshold {self.edge_change_threshold}"
            )
            return False

        # Check 3: Time-based invalidation
        if cache_state["last_rebuild_at"]:
            try:
                cache_age = datetime.now() - datetime.fromisoformat(cache_state["last_rebuild_at"])
                if cache_age > self.ttl:
                    logger.info(f"Cache invalid for repo {self.repo_id}: age {cache_age} exceeds TTL {self.ttl}")
                    return False
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid cache timestamp: {e}")
                return False

        logger.debug(f"Cache valid for repo {self.repo_id}")
        return True

    def _get_cache_state(self) -> dict | None:
        """Get current cache state from database."""
        with Session(self.db) as session:
            statement = select(GraphCacheState).where(GraphCacheState.repo_id == self.repo_id)
            result = session.exec(statement).first()

            if not result:
                return None

            return {
                "commit_sha": result.commit_sha,
                "last_rebuild_at": result.last_rebuild_at,
                "node_count": result.node_count,
                "edge_count": result.edge_count,
                "edge_changes_since_rebuild": result.edge_changes_since_rebuild,
            }

    def _get_current_commit_sha(self) -> str | None:
        """Get current HEAD commit SHA for repository.

        Returns:
            Commit SHA or None if not a git repository
        """
        # Get repo path
        with Session(self.db) as session:
            statement = select(Repo).where(Repo.id == self.repo_id)
            repo = session.exec(statement).first()

            if not repo or not repo.root_path:
                logger.warning(f"Repo {self.repo_id} not found or has no root_path")
                return None

            repo_path = Path(repo.root_path)

        # Check if it's a git repository
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            logger.debug(f"Not a git repository: {repo_path}")
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.warning(f"Git command failed for repo {self.repo_id}: {result.stderr}")
                return None

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to get git SHA for repo {self.repo_id}: {e}")
            return None

    def update_cache_state(
        self,
        commit_sha: str,
        node_count: int,
        edge_count: int,
        reset_changes: bool = True,
    ):
        """Update cache state after rebuild.

        Args:
            commit_sha: Current commit SHA
            node_count: Number of nodes in graph
            edge_count: Number of edges in graph
            reset_changes: Whether to reset edge change counter (default: True)
        """
        with Session(self.db) as session:
            # Get or create cache state
            statement = select(GraphCacheState).where(GraphCacheState.repo_id == self.repo_id)
            cache_state = session.exec(statement).first()

            if cache_state:
                # Update existing
                cache_state.commit_sha = commit_sha
                cache_state.last_rebuild_at = datetime.now().isoformat()
                cache_state.node_count = node_count
                cache_state.edge_count = edge_count
                if reset_changes:
                    cache_state.edge_changes_since_rebuild = 0
            else:
                # Create new
                cache_state = GraphCacheState(
                    repo_id=self.repo_id,
                    commit_sha=commit_sha,
                    last_rebuild_at=datetime.now().isoformat(),
                    node_count=node_count,
                    edge_count=edge_count,
                    edge_changes_since_rebuild=0,
                )
                session.add(cache_state)

            session.commit()

    def increment_edge_changes(self, count: int = 1):
        """Increment edge change counter.

        Args:
            count: Number of edge changes to add (default: 1)
        """
        with Session(self.db) as session:
            statement = select(GraphCacheState).where(GraphCacheState.repo_id == self.repo_id)
            cache_state = session.exec(statement).first()

            if cache_state:
                cache_state.edge_changes_since_rebuild += count
            else:
                # Create initial state if it doesn't exist yet (e.g. first index of a fresh repo)
                cache_state = GraphCacheState(
                    repo_id=self.repo_id,
                    edge_changes_since_rebuild=count,
                    commit_sha="",
                    last_rebuild_at=datetime.now().isoformat(),
                    node_count=0,
                    edge_count=0,
                )
                session.add(cache_state)
            session.commit()
