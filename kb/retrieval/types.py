from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class Document:
    """A dataclass representing a document chunk."""

    chunk_id: str
    content: str
    repo: str
    path: str
    start_line: int
    end_line: int
    language: Optional[str] = None
    symbol_kind: Optional[str] = None
    symbol_name: Optional[str] = None
    symbol_path: Optional[str] = None
    score: Optional[float] = None
    rerank_score: Optional[float] = None
    commit: Optional[str] = None
    branch: Optional[str] = None
    source: Optional[str] = "vector"

    def to_dict(self) -> Dict[str, Any]:
        """Convert the document to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        """Create a document from a dictionary."""
        return cls(**data)