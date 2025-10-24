from __future__ import annotations

from time import perf_counter

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


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/search")
async def search(request: SearchRequest) -> dict[str, object]:
    """Stub search endpoint that returns an empty result set."""
    started = perf_counter()
    latency_ms = int((perf_counter() - started) * 1000)
    _ = request
    return {"hits": [], "meta": {"top_k": request.top_k, "model": request.embed_model, "latency_ms": latency_ms}}


def main() -> None:
    import uvicorn

    uvicorn.run("pb_kb.api.app:app", host="127.0.0.1", port=7777, reload=False)


if __name__ == "__main__":
    main()
