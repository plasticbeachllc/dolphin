#!/usr/bin/env python3
"""Self-contained regression tests for vector and hybrid search flows."""

from __future__ import annotations

from pathlib import Path

import pytest

from kb.api.app import SearchRequest
from kb.api.search_backend import create_search_backend
from kb.hashing import hash_text


def _seed_test_data(backend, embed_model: str = "small") -> tuple[str, str]:
    """Populate SQLite and LanceDB stores with a single deterministic chunk."""

    backend.sql_store.initialize()

    content = "Authentication middleware validates JWT tokens before routing."
    text_hash = hash_text(content)
    chunk_id = f"1:1:{embed_model}:{text_hash}:1:3"

    vector_dim = backend.embedding_provider.model_dimensions[embed_model]
    backend.lance_store.upsert_chunks(
        "test-repo",
        [
            {
                "id": chunk_id,
                "vector": [0.1] * vector_dim,
                "repo": "test-repo",
                "path": "src/auth.py",
                "start_line": 1,
                "end_line": 3,
                "text_hash": text_hash,
                "commit": "",
                "branch": "",
                "embed_model": embed_model,
            }
        ],
        model=embed_model,
    )

    backend.sql_store.index_chunk_for_fts(
        content_id=chunk_id,
        repo="test-repo",
        path="src/auth.py",
        text_hash=text_hash,
        content=content,
    )

    return chunk_id, content


@pytest.fixture()
def populated_backend(tmp_path: Path):
    """Create a fully initialized backend with vector data ready for search."""

    backend = create_search_backend(
        store_root=tmp_path,
        embedding_provider_type="stub",
        hybrid_search_enabled=False,
        default_embed_model="small",  # Set global config to match indexed data
    )

    chunk_id, _ = _seed_test_data(backend, embed_model="small")
    return backend, chunk_id


@pytest.fixture()
def populated_hybrid_backend(tmp_path: Path):
    """Create a backend configured for hybrid search with test data."""

    backend = create_search_backend(
        store_root=tmp_path,
        embedding_provider_type="stub",
        hybrid_search_enabled=True,
        default_embed_model="small",  # Set global config to match indexed data
    )

    chunk_id, _ = _seed_test_data(backend, embed_model="small")
    return backend, chunk_id


def test_vector_search_with_populated_data(populated_backend):
    """Verify vector search returns the seeded chunk without external state."""

    backend, chunk_id = populated_backend
    # No longer pass embed_model - uses global config
    request = SearchRequest(query="authentication", top_k=3)

    results = backend.search(request)

    assert results, "Vector search returned no results"
    assert results[0]["chunk_id"] == chunk_id


def test_hybrid_search_comparison(populated_hybrid_backend):
    """Ensure hybrid search executes alongside vector-only search on the same data."""

    backend, chunk_id = populated_hybrid_backend

    # No longer pass embed_model - uses global config
    request = SearchRequest(query="authentication", top_k=5)

    vector_only = backend
    vector_only.hybrid_search_enabled = False

    vector_results = vector_only.search(request)
    hybrid_results = backend.search(request)

    assert vector_results, "Vector-only search should return results"
    assert hybrid_results, "Hybrid search should return results"
    assert vector_results[0]["chunk_id"] == chunk_id
    assert hybrid_results[0]["chunk_id"] == chunk_id
