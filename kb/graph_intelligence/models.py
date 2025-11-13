"""Domain models for graph intelligence."""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of nodes in the code graph."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    MODULE = "module"
    FILE = "file"
    VARIABLE = "variable"


class EdgeType(str, Enum):
    """Types of edges in the code graph."""

    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    USES = "uses"  # Variable/data usage
    CONTAINS = "contains"  # Module contains class, class contains method
    DEFINES = "defines"  # Function defines variable
    MODIFIES = "modifies"  # Function modifies variable


class GraphNode(BaseModel):
    """Represents a node in the code graph."""

    id: str
    repo_id: int
    node_type: NodeType
    name: str
    qualified_name: Optional[str] = None
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    language: str
    signature: Optional[str] = None
    docstring: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Represents an edge in the code graph."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    attributes: Dict[str, Any] = Field(default_factory=dict)
    repo_id: Optional[int] = None


class GraphMetrics(BaseModel):
    """Computed metrics for a graph node."""

    node_id: str
    pagerank: Optional[float] = None
    betweenness_centrality: Optional[float] = None
    in_degree: int = 0
    out_degree: int = 0
    cyclomatic_complexity: Optional[int] = None
    community_id: Optional[int] = None
