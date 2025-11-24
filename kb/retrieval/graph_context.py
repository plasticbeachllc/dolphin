"""Graph context enrichment for search results.

This module provides functions to enrich search results with code graph context,
including nodes (code entities) and edges (relationships) that overlap with
search result chunks.
"""

from __future__ import annotations

from typing import Any

from kb.store.graph_store import GraphStore
from kb.store.sqlite_meta import SQLiteMetadataStore


class GraphContextEnricher:
    """Enriches search results with code graph context."""

    def __init__(
        self,
        graph_store: GraphStore,
        sql_store: SQLiteMetadataStore,
        max_related_nodes: int = 10,
        max_edges_per_node: int = 5,
    ):
        """Initialize graph context enricher.

        Args:
            graph_store: Graph database store
            sql_store: SQL metadata store
            max_related_nodes: Maximum related nodes to include per result
            max_edges_per_node: Maximum edges to include per node
        """
        self.graph_store = graph_store
        self.sql_store = sql_store
        self.max_related_nodes = max_related_nodes
        self.max_edges_per_node = max_edges_per_node

    def enrich_search_results(
        self,
        results: list[dict[str, Any]],
        include_callsites: bool = True,
        include_implementations: bool = True,
        include_dependencies: bool = True,
    ) -> list[dict[str, Any]]:
        """Enrich search results with graph context.

        Args:
            results: List of search result dicts
            include_callsites: Include incoming call edges
            include_implementations: Include inheritance/implementation edges
            include_dependencies: Include dependency edges

        Returns:
            Enriched results with graph_context field added
        """
        enriched_results = []

        for result in results:
            graph_context = self._get_graph_context_for_result(
                result,
                include_callsites=include_callsites,
                include_implementations=include_implementations,
                include_dependencies=include_dependencies,
            )

            enriched_result = {**result}
            if graph_context:
                enriched_result["graph_context"] = graph_context

            enriched_results.append(enriched_result)

        return enriched_results

    def _get_graph_context_for_result(
        self,
        result: dict[str, Any],
        include_callsites: bool = True,
        include_implementations: bool = True,
        include_dependencies: bool = True,
    ) -> dict[str, Any] | None:
        """Get graph context for a single search result.

        Args:
            result: Search result dict with repo, path, start_line, end_line
            include_callsites: Include incoming call edges
            include_implementations: Include inheritance/implementation edges
            include_dependencies: Include dependency edges

        Returns:
            Graph context dict or None if no graph data available
        """
        try:
            repo = result.get("repo")
            path = result.get("path")
            start_line = result.get("start_line")
            end_line = result.get("end_line")

            if not all([repo, path, start_line is not None, end_line is not None]):
                return None

            # Get file_id from SQL store
            # Type narrowing: repo.get() returns Any | None, cast to str after validation
            repo_str = str(repo) if repo else None
            if not repo_str:
                return None
            repo_info = self.sql_store.get_repo_by_name(repo_str)
            if not repo_info:
                return None

            repo_id = repo_info["id"]
            # Type narrowing: path.get() returns Any | None, cast to str after validation
            path_str = str(path) if path else None
            if not path_str:
                return None
            file_id = self.sql_store.get_file_id(repo_id, path_str)
            if not file_id:
                return None
        except Exception:
            # Handle any errors gracefully by returning None
            return None

        # Get all nodes for this file
        all_nodes = self.graph_store.get_nodes_for_file(file_id)

        # Filter nodes that overlap with the result's line range
        # Type narrowing: start_line and end_line are validated as not None above
        start_line_int = int(start_line) if start_line is not None else 0
        end_line_int = int(end_line) if end_line is not None else 0
        overlapping_nodes = [
            node
            for node in all_nodes
            if self._ranges_overlap(
                int(node["start_line"]) if node.get("start_line") is not None else 0,
                int(node["end_line"]) if node.get("end_line") is not None else 0,
                start_line_int,
                end_line_int,
            )
        ]

        if not overlapping_nodes:
            return None

        # Build graph context
        context = {"nodes": [], "relationships": []}

        for node in overlapping_nodes[: self.max_related_nodes]:
            # Add node info
            node_info = {
                "id": node["id"],
                "type": node["node_type"],
                "name": node["name"],
                "qualified_name": node["qualified_name"],
                "signature": node["signature"],
                "line_range": [node["start_line"], node["end_line"]],
            }
            context["nodes"].append(node_info)

            # Get relationships for this node
            relationships = self._get_relationships_for_node(
                node["id"],
                include_callsites=include_callsites,
                include_implementations=include_implementations,
                include_dependencies=include_dependencies,
            )

            context["relationships"].extend(relationships)

        # Remove duplicate relationships
        context["relationships"] = self._deduplicate_relationships(context["relationships"])

        return context if context["nodes"] else None

    def _get_relationships_for_node(
        self,
        node_id: str,
        include_callsites: bool = True,
        include_implementations: bool = True,
        include_dependencies: bool = True,
    ) -> list[dict[str, Any]]:
        """Get relationships for a node.

        Args:
            node_id: Node UUID
            include_callsites: Include incoming call edges
            include_implementations: Include inheritance/implementation edges
            include_dependencies: Include dependency edges

        Returns:
            List of relationship dicts
        """
        relationships = []

        # Get outgoing edges (what this node calls/uses/extends)
        outgoing_edges = self.graph_store.get_outgoing_edges(node_id, limit=self.max_edges_per_node)

        for edge in outgoing_edges:
            edge_type = edge["edge_type"]

            # Filter by relationship type preferences
            if edge_type == "calls" and not include_callsites:
                continue
            if edge_type in ("inherits", "implements") and not include_implementations:
                continue
            if edge_type in ("imports", "depends_on") and not include_dependencies:
                continue

            # Get target node info
            target_node = self.graph_store.get_node_by_id(edge["target_node_id"])
            if not target_node:
                continue

            relationships.append(
                {
                    "type": edge_type,
                    "direction": "outgoing",
                    "target": {
                        "name": target_node["name"],
                        "qualified_name": target_node["qualified_name"],
                        "node_type": target_node["node_type"],
                        "signature": target_node["signature"],
                    },
                    "line_number": edge["line_number"],
                }
            )

        # Get incoming edges (what calls/uses/extends this node)
        if include_callsites:
            incoming_edges = self.graph_store.get_incoming_edges(
                node_id, edge_type="calls", limit=self.max_edges_per_node
            )

            for edge in incoming_edges:
                # Get source node info
                source_node = self.graph_store.get_node_by_id(edge["source_node_id"])
                if not source_node:
                    continue

                relationships.append(
                    {
                        "type": edge["edge_type"],
                        "direction": "incoming",
                        "source": {
                            "name": source_node["name"],
                            "qualified_name": source_node["qualified_name"],
                            "node_type": source_node["node_type"],
                            "signature": source_node["signature"],
                        },
                        "line_number": edge["line_number"],
                    }
                )

        # Get implementations if requested
        if include_implementations:
            incoming_impl_edges = self.graph_store.get_incoming_edges(
                node_id, edge_type="implements", limit=self.max_edges_per_node
            )

            for edge in incoming_impl_edges:
                source_node = self.graph_store.get_node_by_id(edge["source_node_id"])
                if not source_node:
                    continue

                relationships.append(
                    {
                        "type": edge["edge_type"],
                        "direction": "incoming",
                        "source": {
                            "name": source_node["name"],
                            "qualified_name": source_node["qualified_name"],
                            "node_type": source_node["node_type"],
                            "signature": source_node["signature"],
                        },
                        "line_number": edge["line_number"],
                    }
                )

        return relationships

    def _ranges_overlap(self, start1: int, end1: int, start2: int, end2: int) -> bool:
        """Check if two line ranges overlap.

        Args:
            start1, end1: First range
            start2, end2: Second range

        Returns:
            True if ranges overlap
        """
        return start1 <= end2 and start2 <= end1

    def _deduplicate_relationships(self, relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate relationships.

        Args:
            relationships: List of relationship dicts

        Returns:
            Deduplicated list
        """
        seen = set()
        deduped = []

        for rel in relationships:
            # Create unique key based on relationship attributes
            if rel["direction"] == "outgoing":
                key = (
                    rel["type"],
                    rel["direction"],
                    rel["target"]["qualified_name"],
                    rel.get("line_number"),
                )
            else:
                key = (
                    rel["type"],
                    rel["direction"],
                    rel["source"]["qualified_name"],
                    rel.get("line_number"),
                )

            if key not in seen:
                seen.add(key)
                deduped.append(rel)

        return deduped


def format_graph_context_for_llm(graph_context: dict[str, Any]) -> str:
    """Format graph context into human-readable text for LLM consumption.

    Args:
        graph_context: Graph context dict with nodes and relationships

    Returns:
        Formatted string describing the code graph
    """
    if not graph_context or not graph_context.get("nodes"):
        return ""

    lines = ["## Code Graph Context", ""]

    # Format nodes
    nodes = graph_context.get("nodes", [])
    if nodes:
        lines.append("### Entities in this code:")
        for node in nodes:
            sig = node.get("signature", "")
            sig_str = f" - {sig}" if sig else ""
            lines.append(
                f"- **{node['type']}** `{node['qualified_name']}`{sig_str} "
                f"(lines {node['line_range'][0]}-{node['line_range'][1]})"
            )
        lines.append("")

    # Format relationships grouped by type
    relationships = graph_context.get("relationships", [])
    if relationships:
        # Group by type and direction
        calls_to = [r for r in relationships if r["type"] == "calls" and r["direction"] == "outgoing"]
        called_by = [r for r in relationships if r["type"] == "calls" and r["direction"] == "incoming"]
        inherits = [r for r in relationships if r["type"] == "inherits" and r["direction"] == "outgoing"]
        implements = [r for r in relationships if r["type"] == "implements"]
        imports = [r for r in relationships if r["type"] == "imports" and r["direction"] == "outgoing"]

        if calls_to:
            lines.append("### Calls:")
            for rel in calls_to[:5]:  # Limit to top 5
                target = rel["target"]
                line_info = f" (line {rel['line_number']})" if rel.get("line_number") else ""
                lines.append(f"- → `{target['qualified_name']}`{line_info}")
            lines.append("")

        if called_by:
            lines.append("### Called by:")
            for rel in called_by[:5]:  # Limit to top 5
                source = rel["source"]
                line_info = f" (line {rel['line_number']})" if rel.get("line_number") else ""
                lines.append(f"- ← `{source['qualified_name']}`{line_info}")
            lines.append("")

        if inherits:
            lines.append("### Inherits from:")
            for rel in inherits:
                target = rel["target"]
                lines.append(f"- `{target['qualified_name']}`")
            lines.append("")

        if implements:
            lines.append("### Implementations:")
            for rel in implements:
                if rel["direction"] == "outgoing":
                    target = rel["target"]
                    lines.append(f"- Implements `{target['qualified_name']}`")
                else:
                    source = rel["source"]
                    lines.append(f"- Implemented by `{source['qualified_name']}`")
            lines.append("")

        if imports:
            lines.append("### Dependencies:")
            for rel in imports[:5]:  # Limit to top 5
                target = rel["target"]
                lines.append(f"- `{target['qualified_name']}`")
            lines.append("")

    return "\n".join(lines).strip()
