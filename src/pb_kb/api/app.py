from __future__ import annotations

from inspect import isawaitable
from time import perf_counter
from typing import Awaitable, Iterable, Protocol, Sequence

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Unified Knowledge Store", version="0.1.0")


class SearchRequest(BaseModel):
    query: str
    repos: list[str] | None = None
    path_prefix: list[str] | None = None
    top_k: int = 8
    max_snippet_tokens: int = 240
    embed_model: str = "small"
    score_cutoff: float | None = None


class SearchBackend(Protocol):
    """Protocol describing the dependency used to execute searches."""

    def search(
        self, request: SearchRequest
    ) -> Sequence[dict[str, object]] | Awaitable[Sequence[dict[str, object]]]:
        ...


class _EmptySearchBackend:
    """Default backend that returns zero hits until retrieval is implemented."""

    def search(
        self, request: SearchRequest
    ) -> Sequence[dict[str, object]] | Awaitable[Sequence[dict[str, object]]]:
        _ = request
        return ()


_DEFAULT_BACKEND = _EmptySearchBackend()
_search_backend: SearchBackend = _DEFAULT_BACKEND


def set_search_backend(backend: SearchBackend | None) -> None:
    """Override the search backend used by the API."""
    global _search_backend
    _search_backend = backend or _DEFAULT_BACKEND


def get_search_backend() -> SearchBackend:
    """Return the currently configured search backend."""
    return _search_backend


def reset_search_backend() -> None:
    """Restore the default empty backend."""
    set_search_backend(None)


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/search")
async def search(request: SearchRequest) -> dict[str, object]:
    """Dispatch the search request to the configured backend."""
    backend = get_search_backend()
    started = perf_counter()
    raw_hits = backend.search(request)
    hits: Iterable[dict[str, object]]
    if isawaitable(raw_hits):
        hits = await raw_hits  # type: ignore[assignment]
    else:
        hits = raw_hits
    hits_list = list(hits)
    latency_ms = int((perf_counter() - started) * 1000)
    return {
        "hits": hits_list,
        "meta": {
            "top_k": request.top_k,
            "model": request.embed_model,
            "latency_ms": latency_ms,
            "max_snippet_tokens": request.max_snippet_tokens,
        },
    }


def main() -> None:
    import uvicorn

    uvicorn.run("pb_kb.api.app:app", host="127.0.0.1", port=7777, reload=False)


if __name__ == "__main__":
    main()
