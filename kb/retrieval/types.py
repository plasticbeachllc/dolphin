from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Document:
    """A dataclass representing a document chunk."""

    chunk_id: str
    content: str
    repo: str
    path: str
    start_line: int
    end_line: int
    language: str | None = None
    symbol_kind: str | None = None
    symbol_name: str | None = None
    symbol_path: str | None = None
    score: float | None = None
    rerank_score: float | None = None
    commit: str | None = None
    branch: str | None = None
    source: str | None = "vector"

    def to_dict(self) -> dict[str, Any]:
        """Convert the document to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        """Create a document from a dictionary."""
        return cls(**data)
