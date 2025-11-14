"""Manage NetworkX graph with lazy loading and cache validation."""

import logging
import time
from datetime import datetime

import networkx as nx  # type: ignore[import-untyped]
from sqlmodel import Session, select

from kb.store.sql_models import CodeEdge, CodeNode, GraphMetrics

from .cache_validator import GraphCacheValidator

logger = logging.getLogger(__name__)


class GraphManager:
    """Manage NetworkX graph with lazy loading and intelligent caching."""

    def __init__(
        self,
        db,
        repo_id: int,
        edge_change_threshold: int = 5,
        cache_ttl_minutes: int = 10,
    ):
        """Initialize graph manager.

        Args:
            db: Database connection
            repo_id: Repository ID
            edge_change_threshold: Edge changes before cache invalidation (default: 5)
            cache_ttl_minutes: Cache TTL in minutes (default: 10)
        """
        self.db = db
        self.repo_id = repo_id

        # In-memory cache
        self._graph: nx.DiGraph | None = None
        self._last_rebuild: datetime | None = None

        # Validator
        self.validator = GraphCacheValidator(
            db=db,
            repo_id=repo_id,
            edge_change_threshold=edge_change_threshold,
            ttl_minutes=cache_ttl_minutes,
        )

    def get_graph(self, force_rebuild: bool = False) -> nx.DiGraph:
        """Get NetworkX graph, rebuilding if necessary.

        Args:
            force_rebuild: Force rebuild even if cache is valid (default: False)

        Returns:
            NetworkX directed graph
        """
        # Check if rebuild needed
        if force_rebuild or self._graph is None or not self.validator.is_cache_valid():
            logger.info(f"Rebuilding graph for repo {self.repo_id}")
            self._rebuild_graph()

        return self._graph

    def _rebuild_graph(self):
        """Rebuild NetworkX graph from SQLite edges."""
        start_time = time.time()

        # Get current repo state
        current_commit = self.validator._get_current_commit_sha() or "unknown"

        # Fetch all nodes and edges from SQLite
        nodes = self._fetch_nodes_from_db()
        edges = self._fetch_edges_from_db()

        # Build graph
        G = nx.DiGraph()

        for node in nodes:
            G.add_node(
                node["id"],
                node_type=node.get("node_type"),
                name=node.get("name"),
                qualified_name=node.get("qualified_name"),
                file_id=node.get("file_id"),
                language=node.get("language"),
                commit_sha=node.get("commit_sha"),
                branch=node.get("branch"),
            )

        for edge in edges:
            G.add_edge(
                edge["source_node_id"],
                edge["target_node_id"],
                edge_type=edge["edge_type"],
                commit_sha=edge.get("commit_sha"),
                line_number=edge.get("line_number"),
                is_direct=edge.get("is_direct"),
                metadata=edge.get("relationship_metadata"),
            )

        # Update cache
        self._graph = G
        self._last_rebuild = datetime.now()

        # Update cache state in DB
        self.validator.update_cache_state(
            commit_sha=current_commit,
            node_count=G.number_of_nodes(),
            edge_count=G.number_of_edges(),
            reset_changes=True,
        )

        elapsed = time.time() - start_time
        logger.info(
            f"Graph rebuilt for repo {self.repo_id}: "
            f"{G.number_of_nodes()} nodes, "
            f"{G.number_of_edges()} edges in {elapsed:.2f}s"
        )

    def _fetch_nodes_from_db(self) -> list[dict]:
        """Fetch all graph nodes from database."""

        nodes: list[dict] = []

        with Session(self.db) as session:
            statement = select(CodeNode).where(CodeNode.repo_id == self.repo_id)
            results = session.exec(statement).all()

            for node in results:
                nodes.append(
                    {
                        "id": node.id,
                        "node_type": node.node_type,
                        "name": node.name,
                        "qualified_name": node.qualified_name,
                        "file_id": node.file_id,
                        "language": node.language,
                        "commit_sha": node.commit_sha,
                        "branch": node.branch,
                    }
                )

        return nodes

    def _fetch_edges_from_db(self) -> list[dict]:
        """Fetch all graph edges from database.

        Returns:
            List of edge dictionaries
        """
        edges = []

        with Session(self.db) as session:
            statement = select(CodeEdge).where(CodeEdge.repo_id == self.repo_id)
            results = session.exec(statement).all()

            for edge in results:
                edges.append(
                    {
                        "source_node_id": edge.source_node_id,
                        "target_node_id": edge.target_node_id,
                        "edge_type": edge.edge_type,
                        "commit_sha": edge.commit_sha,
                        "line_number": edge.line_number,
                        "is_direct": edge.is_direct,
                        "relationship_metadata": edge.relationship_metadata,
                    }
                )

        return edges

    def on_edges_changed(self, count: int):
        """Track edge changes for cache invalidation.

        Args:
            count: Number of edge changes
        """
        self.validator.increment_edge_changes(count)
        logger.debug(f"Tracked {count} edge changes for repo {self.repo_id}")

    def invalidate_cache(self):
        """Manually invalidate the in-memory cache."""
        self._graph = None
        self._last_rebuild = None
        logger.info(f"Cache manually invalidated for repo {self.repo_id}")

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        cache_state = self.validator._get_cache_state()

        return {
            "repo_id": self.repo_id,
            "is_loaded": self._graph is not None,
            "is_valid": self.validator.is_cache_valid() if self._graph else False,
            "last_rebuild": (self._last_rebuild.isoformat() if self._last_rebuild else None),
            "node_count": self._graph.number_of_nodes() if self._graph else 0,
            "edge_count": self._graph.number_of_edges() if self._graph else 0,
            "cache_state": cache_state,
        }

    def compute_metrics(self) -> dict:
        """Compute graph metrics (PageRank, centrality, etc.).

        Returns:
            Dictionary of computed metrics
        """
        # Use existing graph if loaded, otherwise load it
        if self._graph is None:
            graph = self.get_graph()
        else:
            graph = self._graph

        if graph.number_of_nodes() == 0:
            logger.warning(f"Cannot compute metrics: empty graph for repo {self.repo_id}")
            return {}

        logger.info(f"Computing metrics for repo {self.repo_id}")
        start_time = time.time()

        metrics = {}

        # PageRank
        try:
            pagerank = nx.pagerank(graph, alpha=0.85, max_iter=100)
            metrics["pagerank"] = pagerank
        except Exception as e:
            logger.warning(f"PageRank computation failed: {e}")

        # Betweenness centrality (sample for large graphs)
        try:
            if graph.number_of_nodes() > 1000:
                # Sample for performance
                betweenness = nx.betweenness_centrality(graph, k=min(100, graph.number_of_nodes()))
            else:
                betweenness = nx.betweenness_centrality(graph)
            metrics["betweenness_centrality"] = betweenness
        except Exception as e:
            logger.warning(f"Betweenness centrality computation failed: {e}")

        # Degree metrics
        try:
            in_degree = dict(graph.in_degree())
            out_degree = dict(graph.out_degree())
            metrics["in_degree"] = in_degree
            metrics["out_degree"] = out_degree
        except Exception as e:
            logger.warning(f"Degree computation failed: {e}")

        # Community detection (if python-louvain available)
        try:
            import community as community_louvain

            # Convert to undirected for community detection
            undirected = graph.to_undirected()
            partition = community_louvain.best_partition(undirected)
            metrics["community"] = partition
        except ImportError:
            logger.debug("python-louvain not available, skipping community detection")
        except Exception as e:
            logger.warning(f"Community detection failed: {e}")

        elapsed = time.time() - start_time
        logger.info(f"Metrics computed in {elapsed:.2f}s")

        return metrics

    def store_metrics(self, metrics: dict):
        """Store computed metrics in database.

        Args:
            metrics: Dictionary of metrics from compute_metrics()
        """
        logger.info(f"Storing metrics for repo {self.repo_id}")
        computed_at = datetime.now().isoformat()

        with Session(self.db) as session:
            # Get all unique node IDs
            pagerank = metrics.get("pagerank", {})
            betweenness = metrics.get("betweenness_centrality", {})
            in_degree = metrics.get("in_degree", {})
            out_degree = metrics.get("out_degree", {})
            community = metrics.get("community", {})

            all_nodes = set(pagerank.keys()) | set(betweenness.keys()) | set(in_degree.keys())

            for node_id in all_nodes:
                # Check if metrics record exists
                statement = select(GraphMetrics).where(GraphMetrics.node_id == node_id)
                existing = session.exec(statement).first()

                if existing:
                    # Update
                    existing.pagerank = pagerank.get(node_id)
                    existing.betweenness_centrality = betweenness.get(node_id)
                    existing.in_degree = in_degree.get(node_id, 0)
                    existing.out_degree = out_degree.get(node_id, 0)
                    existing.community_id = community.get(node_id)
                    existing.computed_at = computed_at
                else:
                    # Create new
                    new_metrics = GraphMetrics(
                        node_id=node_id,
                        pagerank=pagerank.get(node_id),
                        betweenness_centrality=betweenness.get(node_id),
                        in_degree=in_degree.get(node_id, 0),
                        out_degree=out_degree.get(node_id, 0),
                        community_id=community.get(node_id),
                        computed_at=computed_at,
                    )
                    session.add(new_metrics)

            session.commit()
            logger.info(f"Stored metrics for {len(all_nodes)} nodes")
