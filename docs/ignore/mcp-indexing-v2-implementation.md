# MCP Indexing v2 — Detailed Implementation Plan (v0.4)

Status: Implementation Plan
Owner: Taylor Cathcart
Date: 2025-10-30

---

Goals and scope
- Build a local-first code/doc retrieval stack for dogfooding (MacBook Pro M4 Pro, 24 GB RAM).
- Sources: repository code and Markdown only. Languages prioritized: TypeScript, Python; Markdown; fallback line windowing for others.
- Embeddings: OpenAI text-embedding-3-small by default; per-repo override to 3-large. Single-vector per chunk via labeled concatenation of code + docstring + signature.
- Storage: LanceDB for vectors + SQLite for metadata under ~/.dolphin/knowledge_store.
- Interfaces: CLI (kb) for ingestion; FastAPI Retriever (/v1/search); MCP wrapper for OpenWebUI; Continue context provider.
- Constraints: Keep it simple; leave seams for upgrades (BM25 hybrid, reranking, watch mode, graph).

References
- Architecture: docs/mcp_indexing_architecture_detailed.md (v0.4)
- Sprint scope: docs/unified-knowledge-store-sprint-1.prompt.md
- MCP bridge: docs/phase-5-mcp-bridge-spec.md
- Code: mcp-bridge/, src/pb_kb/

---

Milestones and acceptance criteria
- M0: bootstrap and schemas
  - kb init creates store root and SQLite with tables; LanceDB collection created.
- M1: end-to-end indexing (single repo)
  - kb index completes; unchanged chunks skipped; vectors+metadata persisted; cost ledger recorded.
- M2: retriever API online
  - POST /v1/search returns top_k ranked hits with provenance within target latency on small data.
- M3: MCP + Continue integration
  - search_knowledge works in OpenWebUI; Continue can pull snippets.
- M4: evaluation harness and metrics
  - Precision@5, Recall@10, MRR, latency p50/p95 reported for a 15–20 query set.
- M5: optional post-commit hook prototype
  - Local git hook triggers kb index for changed repo respecting budget cap.

---

Project layout (monorepo-friendly)

```text
pyproject.toml
src/pb_kb/
  __init__.py
  config.py
  hashing.py
  ignores.py
  chunkers/
    __init__.py
    ts_chunker.py
    py_chunker.py
    md_chunker.py
    fallback_chunker.py
    repo_config.py      # per-repo chunking configuration
    registry.py         # chunker registry and routing
    token_utils.py
    types.py            # Chunk dataclass and enums
  embeddings.py
  store/
    lancedb_store.py
    sqlite_meta.py
  ingest/
    scanner.py
    pipeline.py
    cli.py              # Typer entrypoint: kb
  api/
    app.py              # FastAPI retriever
  mcp/
    retriever_tool.py   # MCP wrapper (pass-through)
```

---

1) Configuration system
- Global config file: ~/.dolphin/config.toml
- Per-repo config: <repo>/.dolphin/chunking_config.toml
- Precedence: repo overrides global; defaults baked-in as last resort.

```python src/pb_kb/config.py
from dataclasses import dataclass
from pathlib import Path
import tomllib

DEFAULTS = {
    "storage": {"store_root": "~/.dolphin/knowledge_store"},
    "chunking": {"default_window_size": 350, "overlap_pct": 0.10, "per_language": {"python": 512, "typescript": 350, "markdown": 256}},
    "embeddings": {"model": "text-embedding-3-small", "concurrency": 3, "per_session_spend_cap_usd": 10.0},
    "retrieval": {"top_k": 8, "score_cutoff": 0.15, "max_snippet_tokens": 240},
}

@dataclass
class KBConfig:
    store_root: Path
    # ... add other resolved fields as needed

def load_global_config() -> dict:
    p = Path("~/.dolphin/config.toml").expanduser()
    if not p.exists():
        return DEFAULTS
    return {**DEFAULTS, **tomllib.loads(p.read_text())}

def load_repo_config(repo_root: Path) -> dict:
    p = repo_root / ".dolphin" / "chunking_config.toml"
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text())

def resolve_config(repo_root: Path) -> KBConfig:
    g = load_global_config()
    r = load_repo_config(repo_root)
    merged = g | r  # shallow merge is fine for v0
    return KBConfig(store_root=Path(merged["storage"]["store_root"]).expanduser())
```

---

2) SQLite + LanceDB schemas
- SQLite (knowledge.db): repos, files, sessions, chunks_meta (see sprint doc).
- Indices: files(repo_id, path), chunks_meta(repo_id, file_id, text_hash).
- LanceDB: single collection "chunks" with metadata columns + embedding vector.

```python src/pb_kb/store/sqlite_meta.py
import sqlite3
from pathlib import Path

DDL = [
    """
    CREATE TABLE IF NOT EXISTS repos(
      id INTEGER PRIMARY KEY,
      name TEXT UNIQUE,
      path TEXT,
      default_embed_model TEXT,
      created_at TEXT,
      updated_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS files(
      id INTEGER PRIMARY KEY,
      repo_id INTEGER,
      path TEXT,
      lang TEXT,
      last_commit_sha TEXT,
      last_indexed_at TEXT,
      UNIQUE(repo_id, path)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions(
      id INTEGER PRIMARY KEY,
      repo_id INTEGER,
      started_at TEXT,
      ended_at TEXT,
      commit_sha TEXT,
      embed_model TEXT,
      tokens INTEGER,
      estimated_cost_usd REAL,
      success INTEGER
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks_meta(
      id TEXT PRIMARY KEY,
      repo_id INTEGER,
      file_id INTEGER,
      text_hash TEXT,
      start_line INTEGER,
      end_line INTEGER,
      symbol_kind TEXT,
      symbol_name TEXT,
      symbol_path TEXT,
      embed_model TEXT,
      indexed_at TEXT
    );
    """,
]

def init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for stmt in DDL:
        cur.executescript(stmt)
    conn.commit()
    conn.close()
```

```python src/pb_kb/store/lancedb_store.py
from lancedb import connect
from typing import Any

COLUMNS = {
    "id": str,
    "repo_name": str,
    "path": str,
    "lang": str,
    "symbol_kind": str,
    "symbol_name": str,
    "symbol_path": str,
    "start_line": int,
    "end_line": int,
    "chunk_index": int,
    "text_hash": str,
    "commit_sha": str,
    "indexed_at": str,
    "embedding": list,  # VECTOR<float32> [dims]
    "content": str,
}

def ensure_chunks_table(store_root: str):
    db = connect(store_root)
    if "chunks" not in db.table_names():
        db.create_table("chunks", data=[{k: None for k in COLUMNS.keys()}])
    return db.open_table("chunks")

def upsert_chunks(table, rows: list[dict[str, Any]]):
    # For MVP we can just insert; dedupe handled by hash upstream
    table.add(rows)
```

---

3) Ignore and scanning
- Honor .gitignore and default ignore sets.
- Map file extensions to language using registry.

```python src/pb_kb/ingest/scanner.py
from pathlib import Path
from pathspec import PathSpec

DEFAULT_IGNORES = [
    "node_modules/**","dist/**","build/**",".next/**",".venv/**",
    ".mypy_cache/**",".pytest_cache/**",".DS_Store",".env",".env.*",
    ".secrets","coverage",".cache/**","target/**","vendor/**"
]

def load_gitignore(repo_root: Path) -> PathSpec:
    gi = repo_root / ".gitignore"
    patterns = DEFAULT_IGNORES + (gi.read_text().splitlines() if gi.exists() else [])
    return PathSpec.from_lines("gitwildmatch", patterns)

def discover_files(repo_root: Path) -> list[Path]:
    spec = load_gitignore(repo_root)
    files = []
    for p in repo_root.rglob("*"):
        if p.is_file() and not spec.match_file(p.relative_to(repo_root).as_posix()):
            files.append(p)
    return files
```

---

4) Chunking
- TS/Python: tree-sitter to emit symbol-bounded chunks; Markdown by headings; fallback line-windowing.
- Target token window: 350 (configurable); overlap 10%.
- For long functions, multi-chunk with overlap; track chunk_index/total.
- Labeled concatenation for embedding input: code + [DOCSTRING] + [SIGNATURE].

```python src/pb_kb/chunkers/types.py
from dataclasses import dataclass

@dataclass
class Chunk:
    repo: str
    path: str
    lang: str
    start_line: int
    end_line: int
    symbol_kind: str | None
    symbol_name: str | None
    symbol_path: str | None
    chunk_index: int
    total_chunks: int
    text_hash: str
    content: str          # snippet text
    docstring: str | None
    signature: str | None
```

```python src/pb_kb/chunkers/registry.py
EXT_TO_LANG = {"py": "python", "ts": "typescript", "md": "markdown"}

def detect_lang(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    return EXT_TO_LANG.get(ext, "unknown")

def chunk_file(path: str, lang: str, config) -> list:
    if lang == "python":
        return chunk_python(path, config)
    if lang == "typescript":
        return chunk_typescript(path, config)
    if lang == "markdown":
        return chunk_markdown(path, config)
    return chunk_fallback(path, config)
```

---

5) Hashing and idempotency
- Canonicalize content: normalize line endings; strip trailing whitespace.
- Compute SHA256 per chunk content; unchanged hashes are skipped.

```python src/pb_kb/hashing.py
import hashlib

def canonicalize(text: str) -> str:
    return "\n".join([ln.rstrip() for ln in text.replace("\r\n","\n").replace("\r","\n").split("\n")])

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

---

6) Embeddings and cost control
- Single-vector per chunk using labeled concatenation.
- Concurrency 2–4; exponential backoff on 429/5xx; per-session spend cap.

```python src/pb_kb/embeddings.py
from typing import Sequence
import tiktoken

def build_embed_input(code: str, doc: str | None, sig: str | None) -> str:
    return f"""{code}\n\n[DOCSTRING]\n{doc or '(no docstring)'}\n\n[SIGNATURE]\n{sig or ''}\n"""

def estimate_tokens(texts: Sequence[str], encoding: str = "cl100k_base") -> int:
    enc = tiktoken.get_encoding(encoding)
    return sum(len(enc.encode(t)) for t in texts)

async def embed_batch_openai(texts: Sequence[str], model: str, concurrency: int = 3) -> list[list[float]]:
    # Pseudocode: use asyncio.Semaphore(concurrency); retry with backoff on 429/5xx
    # Return list of vectors in same order as texts
    ...
```

---

7) Persisting to stores
- LanceDB upsert (simple add; rely on hash/idempotency upstream).
- SQLite chunks_meta insert/update; files last_commit_sha update.

```python src/pb_kb/store/lancedb_store.py
from datetime import datetime

def rows_from_chunks(repo_name: str, commit_sha: str, chunks: list[dict], embeddings: list[list[float]]):
    now = datetime.utcnow().isoformat() + "Z"
    rows = []
    for c, emb in zip(chunks, embeddings):
        rows.append({
            "id": c["id"],
            "repo_name": repo_name,
            "path": c["path"],
            "lang": c["lang"],
            "symbol_kind": c.get("symbol_kind"),
            "symbol_name": c.get("symbol_name"),
            "symbol_path": c.get("symbol_path"),
            "start_line": c["start_line"],
            "end_line": c["end_line"],
            "chunk_index": c["chunk_index"],
            "text_hash": c["text_hash"],
            "commit_sha": commit_sha,
            "indexed_at": now,
            "embedding": emb,
            "content": c["content"],
        })
    return rows
```

---

8) Indexing pipeline (CLI)
- Steps: scan → detect lang → chunk → canonicalize+hash → skip unchanged → build embed inputs → embed → persist → ledger.
- Diff-based incremental: optionally accept old/new commit and only process changed files.
- Resume on failure via sessions + checkpoint file.

```python src/pb_kb/ingest/pipeline.py
from pathlib import Path
from .scanner import discover_files
from ..chunkers.registry import detect_lang, chunk_file
from ..hashing import canonicalize, sha256
from ..embeddings import build_embed_input, embed_batch_openai
from ..store.lancedb_store import ensure_chunks_table, upsert_chunks, rows_from_chunks

async def index_repo(repo_name: str, repo_path: Path, commit_sha: str, model: str, max_usd: float):
    files = discover_files(repo_path)
    chunks, embed_inputs = [], []
    for f in files:
        lang = detect_lang(str(f))
        for ch in chunk_file(str(f), lang, config=None):
            text = canonicalize(ch.content)
            ch.text_hash = sha256(text)
            ch.content = text
            ch.id = f"{repo_name}:{ch.path}:{ch.start_line}:{ch.end_line}:{ch.text_hash}"
            # TODO: skip unchanged via SQLite lookup on text_hash
            chunks.append(ch)
            embed_inputs.append(build_embed_input(ch.content, ch.docstring, ch.signature))
    vecs = await embed_batch_openai(embed_inputs, model=model, concurrency=3)
    table = ensure_chunks_table(str(Path("~/.dolphin/knowledge_store").expanduser()))
    rows = rows_from_chunks(repo_name, commit_sha, [c.__dict__ for c in chunks], vecs)
    upsert_chunks(table, rows)
    # TODO: write SQLite metadata and sessions ledger
```

```python src/pb_kb/ingest/cli.py
import typer
from pathlib import Path
import asyncio
from .pipeline import index_repo

app = typer.Typer(name="kb")

@app.command()
def init():
    """Create store root and initialize DBs."""
    # mkdir -p ~/.dolphin/knowledge_store and init SQLite/LanceDB
    ...

@app.command("add-repo")
def add_repo(name: str, path: str, default_embed_model: str = "small"):
    """Register a repo by name and path."""
    ...

@app.command()
def index(name: str, commit: str = "HEAD", embed_model: str = "small", max_cost: float = 10.0):
    """Index a repository by name."""
    # Lookup repo path by name in SQLite, resolve commit SHA, call pipeline
    asyncio.run(index_repo(name, Path("/path/from/sqlite"), commit, embed_model, max_cost))
```

---

9) Retriever API (FastAPI)
- POST /v1/search: embed query with model matching collection; KNN in LanceDB; filter by repo/path; return top_k with snippet and provenance.

```python src/pb_kb/api/app.py
from fastapi import FastAPI
from pydantic import BaseModel
from time import perf_counter

app = FastAPI()

class SearchRequest(BaseModel):
    query: str
    repos: list[str] | None = None
    path_prefix: list[str] | None = None
    top_k: int = 8
    max_snippet_tokens: int = 240
    embed_model: str = "small"
    score_cutoff: float | None = 0.15

@app.get('/v1/health')
def health():
    return {"status": "ok"}

@app.post('/v1/search')
def search(req: SearchRequest):
    t0 = perf_counter()
    # 1) Embed query with model for collection
    # 2) Build filter over repo/path
    # 3) LanceDB KNN search (top_k)
    # 4) Truncate snippets to max_snippet_tokens
    # 5) Return hits with provenance and latency
    latency_ms = int((perf_counter() - t0) * 1000)
    return {"hits": [], "meta": {"top_k": req.top_k, "model": req.embed_model, "latency_ms": latency_ms}}
```

---

10) MCP Wrapper (pass-through)
- Tool: search_knowledge; parameters per docs/phase-5-mcp-bridge-spec.md.
- Behavior: forward to POST /v1/search on localhost; return hits[].

```python src/pb_kb/mcp/retriever_tool.py
# Pseudocode: implement MCP tool handler that accepts {query, repos, path_prefix, top_k, max_snippet_tokens, embed_model}
# and forwards to retriever API, returning hits[] or error.
...
```

---

11) Evaluation harness and metrics
- Maintain a small set of 15–20 manual queries + expected anchors.
- Report Precision@5, Recall@10, MRR, and latency percentiles.

```python src/pb_kb/api/eval.py
from typing import Sequence

def precision_at_k(relevant: set[str], results: Sequence[str], k: int) -> float:
    return sum(1 for r in results[:k] if r in relevant) / max(1, min(k, len(results)))

def recall_at_k(relevant: set[str], results: Sequence[str], k: int) -> float:
    return sum(1 for r in results[:k] if r in relevant) / max(1, len(relevant))

def mrr(relevants: list[set[str]], result_lists: list[list[str]]) -> float:
    total = 0.0
    for rel, res in zip(relevants, result_lists):
        rank = next((i+1 for i, r in enumerate(res) if r in rel), 0)
        total += (1.0 / rank) if rank else 0.0
    return total / max(1, len(result_lists))
```

---

12) Post-commit hook (prototype)
- Simple local hook invoking `kb index <name> --commit $(git rev-parse HEAD)` with budget cap.
- Later: background queue single worker to serialize jobs and handle backpressure.

```bash docs/examples/git-hooks/post-commit
#!/bin/sh
kb index REPO_NAME --commit $(git rev-parse HEAD) --max-cost 10.0 || echo "Indexing failed"
```

---

13) Observability and failure recovery
- Logging: index-time (files scanned, chunks created/skipped, tokens, cost), query-time (latency, top_k, filters, hit counts).
- Failure recovery: session ledger with processed files; checkpoint file to resume.

```python src/pb_kb/ingest/pipeline.py
class IndexCheckpoint:
    def __init__(self, repo: str, commit: str):
        self.path = Path(f"/tmp/kb_index_{repo}_{commit}.json")
    def load(self) -> set[str]:
        return set(json.loads(self.path.read_text())["processed"]) if self.path.exists() else set()
    def save(self, processed: set[str]):
        self.path.write_text(json.dumps({"processed": list(processed)}))
```

---

14) Risks and mitigations
- Embedding cost: dedupe unchanged chunks aggressively; per-session cap; preview projected cost before embedding.
- Performance: batch LanceDB writes; add SQLite indices; keep chunk windows modest; avoid oversized snippets.
- Model mismatch: ensure request model matches collection model; validate at /v1/search.
- WAN latency: reuse OpenAI HTTP connections; small concurrency to hide latency.

---

Defer-to-future seams
- Hybrid retrieval (BM25 + vector) and fusion weights
- Graph overlay and expansion; edge confidence calibration
- Learned reranker for top-K
- Parallel indexing worker pool + advanced backpressure
- LSH/minhash for large-K semantic dedupe
- Access control/visibility enforcement
- Packaging (pipx/Docker) and deployment profiles

---

Acceptance checklist per milestone
- M0: kb init succeeds; SQLite + LanceDB created; config resolved.
- M1: kb index repo on TS/Py/MD; unchanged chunks skipped; costs logged; data visible in both stores.
- M2: /v1/search operational; returns plausible hits and logs latency; path scoping works.
- M3: MCP tool and Continue integration retrieve snippets into prompts.
- M4: Eval harness reports metrics; simple regression detection.
- M5: Post-commit hook triggers index; respects cost cap; queueing considered for later.
