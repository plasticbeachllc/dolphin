"""Benchmark tests validating search filtering performance."""

from __future__ import annotations

import random
from typing import cast

from kb.api.app import SearchRequest
from kb.api.search_backend import KnowledgeSearchBackend
from kb.embeddings.provider import EmbeddingProvider
from kb.store.lancedb_store import LanceDBStore
from kb.store.sqlite_meta import SQLiteMetadataStore
from tests.unit.search.legacy_filtering import legacy_filter_and_score


def _make_backend() -> KnowledgeSearchBackend:
    return KnowledgeSearchBackend(
        embedding_provider=cast(EmbeddingProvider, None),
        lance_store=cast(LanceDBStore, None),
        sql_store=cast(SQLiteMetadataStore, None),
    )


def _generate_mock_results(count: int) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for idx in range(count):
        repo = "repo1" if idx % 2 == 0 else "repo2"
        base_path = "src" if idx % 3 != 0 else "tests"
        ext = ".py"
        if idx % 10 == 0:
            ext = ".toml"
        elif idx % 15 == 0:
            ext = ".yaml"
        path = f"{base_path}/module_{idx}{ext}"
        results.append(
            {
                "chunk_id": str(idx),
                "repo": repo,
                "path": path,
                "score": 1.0 - (idx / count),
            }
        )
    rng = random.Random(1337)
    rng.shuffle(results)
    return results


def test_single_pass_filtering_performance() -> None:
    backend = _make_backend()
    results = _generate_mock_results(20000)
    request = SearchRequest(query="demo")

    legacy = legacy_filter_and_score(results, request)
    combined = backend._filter_and_score_results(results, request)

    assert combined == legacy

    legacy_operations = len(results) + len(legacy)
    single_pass_operations = len(results)
    improvement = legacy_operations / single_pass_operations

    assert improvement > 1.5, f"Expected >1.5x improvement, observed {improvement:.2f}x"
