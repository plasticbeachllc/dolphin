from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from kb.api.app import SearchRequest, reset_search_backend, set_search_backend
from kb.hashing import hash_text

FIXTURE_REPO_ROOT = Path(__file__).resolve().parent / "fixtures" / "kb_sample_repo"


@dataclass(slots=True)
class FixtureChunk:
    """Represents a loaded chunk from the sample repository."""

    repo: str
    path: str
    text: str
    start_line: int
    end_line: int
    text_hash: str


class InMemoryKBBackend:
    """Simple in-memory search backend tailored for fixture-driven tests."""

    def __init__(
        self,
        repo_root: Path,
        *,
        repo_name: str = "kb-fixture",
        commit_sha: str = "fixture-main",
    ) -> None:
        self.repo_root = repo_root
        self.repo_name = repo_name
        self.commit_sha = commit_sha
        self._chunks: list[FixtureChunk] = list(self._load_chunks())

    def _load_chunks(self) -> Iterator[FixtureChunk]:
        """Load each text file in the fixture repo as a single chunk."""
        for path in sorted(self.repo_root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".md"}:
                # Mirror early ignore behavior by skipping env files and binaries.
                continue
            text = path.read_text(encoding="utf-8")
            relative_path = path.relative_to(self.repo_root).as_posix()
            lines = text.splitlines()
            end_line = len(lines) if lines else 1
            yield FixtureChunk(
                repo=self.repo_name,
                path=relative_path,
                text=text,
                start_line=1,
                end_line=end_line,
                text_hash=hash_text(text),
            )

    def search(self, request: SearchRequest) -> Sequence[dict[str, object]]:
        """Perform a naive substring search across the loaded chunks."""
        scope = {s.lower() for s in request.repos or []}
        query = request.query.lower()
        matches: list[dict[str, object]] = []
        for chunk in self._chunks:
            if scope and chunk.repo.lower() not in scope:
                continue
            if query not in chunk.text.lower():
                continue
            snippet, truncated, snippet_tokens, total_tokens = _build_snippet(
                chunk.text,
                request.max_snippet_tokens,
                query=request.query,
            )
            score = round(1.0 - (len(matches) * 0.05), 2)
            matches.append(
                {
                    "repo": chunk.repo,
                    "path": chunk.path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "score": score,
                    "snippet": snippet,
                    "truncated": truncated,
                    "snippet_tokens": snippet_tokens,
                    "total_tokens": total_tokens,
                    "provenance": {
                        "commit": self.commit_sha,
                        "text_hash": chunk.text_hash,
                    },
                }
            )
        return matches[: request.top_k]


def _build_snippet(
    text: str,
    max_tokens: int,
    *,
    query: str | None = None,
) -> tuple[str, bool, int, int]:
    """Return snippet text plus truncation metadata given a token budget."""
    snippet_source = text
    if query:
        lower_text = text.lower()
        lower_query = query.lower()
        match_index = lower_text.find(lower_query)
        if match_index >= 0:
            context_window = 160
            start = max(0, match_index - context_window)
            end = min(len(text), match_index + len(query) + context_window)
            snippet_source = text[start:end]
    tokens = snippet_source.split()
    total_tokens = len(tokens)
    if max_tokens <= 0:
        return "", total_tokens > 0, 0, total_tokens
    if total_tokens <= max_tokens:
        snippet_tokens = tokens
        return " ".join(snippet_tokens), False, len(snippet_tokens), total_tokens

    lower_query = (query or "").lower()
    lower_tokens = [token.lower() for token in tokens]
    query_terms = [term for term in lower_query.split() if term]

    if query_terms:
        matched_indices: list[int] = []
        for term in query_terms:
            for idx, token in enumerate(lower_tokens):
                if term in token:
                    matched_indices.append(idx)
                    break
        if matched_indices:
            min_idx = min(matched_indices)
            max_idx = max(matched_indices)
            start = max(0, min_idx - max_tokens // 2)
            end = start + max_tokens
            if end < max_idx + 1:
                end = max_idx + 1
                start = max(0, end - max_tokens)
            if end > total_tokens:
                end = total_tokens
                start = max(0, end - max_tokens)
            snippet_tokens = tokens[start:end]
            return " ".join(snippet_tokens), True, len(snippet_tokens), total_tokens

    snippet_tokens = tokens[:max_tokens]
    snippet = " ".join(snippet_tokens)
    return snippet, True, len(snippet_tokens), total_tokens


@contextmanager
def kb_backend_context(
    *,
    repo_name: str = "kb-fixture",
    commit_sha: str = "fixture-main",
) -> Iterator[InMemoryKBBackend]:
    """Context manager that installs the in-memory backend for tests."""
    backend = InMemoryKBBackend(
        FIXTURE_REPO_ROOT, repo_name=repo_name, commit_sha=commit_sha
    )
    set_search_backend(backend)
    try:
        yield backend
    finally:
        reset_search_backend()
