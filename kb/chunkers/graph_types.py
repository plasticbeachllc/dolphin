"""Standardized graph data structures for code graph extraction.

This module defines common types used across all chunkers for extracting
code graph nodes and edges. These structures enable building a comprehensive
code graph database for tracking relationships, callsites, and dependencies.
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = ["GraphNode", "GraphEdge"]


class GraphNode(NamedTuple):
    """A node in the code graph representing a code entity.
    
    Attributes:
        node_type: Type of entity (class, function, method, table, component, etc.)
        name: Simple name of the entity
        qualified_name: Fully qualified name (e.g., "Module.Class.method")
        start_line: Starting line number (1-based)
        end_line: Ending line number (1-based)
    """
    node_type: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int


class GraphEdge(NamedTuple):
    """An edge in the code graph representing a relationship between entities.
    
    Attributes:
        source_name: Name of the source entity
        target_name: Name of the target entity
        edge_type: Type of relationship (calls, imports, references_table, depends_on, etc.)
        line_number: Line number where the relationship occurs (1-based)
    """
    source_name: str
    target_name: str
    edge_type: str
    line_number: int