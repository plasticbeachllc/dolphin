"""Unit tests for the single-pass filtering and scoring helper."""

from __future__ import annotations

from typing import cast

import pytest

from kb.api.app import SearchRequest
from kb.api.search_backend import KnowledgeSearchBackend
from kb.constants.retrieval_config import RETRIEVAL_PARAMS
from kb.embeddings.provider import EmbeddingProvider
from kb.store.lancedb_store import LanceDBStore
from kb.store.sqlite_meta import SQLiteMetadataStore

from .legacy_filtering import legacy_filter_and_score


class TestFilterAndScore:
    """Validate combined filtering/scoring behaviour."""

    def _backend(self) -> KnowledgeSearchBackend:
        return KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

    def test_combined_logic_matches_legacy_pipeline(self) -> None:
        backend = self._backend()
        results = [
            {"chunk_id": "1", "repo": "repo", "path": "src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "repo", "path": "src/config.toml", "score": 0.8},
            {"chunk_id": "3", "repo": "repo", "path": "tests/test_main.py", "score": 0.7},
        ]
        request = SearchRequest(
            query="demo",
            path_prefix=["src/"],
            exclude_patterns=["*test_*.py"],
        )

        expected = legacy_filter_and_score(results, request)
        combined = backend._filter_and_score_results(results, request)

        assert combined == expected

    def test_config_files_receive_score_penalty(self) -> None:
        backend = self._backend()
        results = [
            {"chunk_id": "1", "repo": "repo", "path": "src/main.py", "score": 1.0},
            {"chunk_id": "2", "repo": "repo", "path": "src/settings.yaml", "score": 0.5},
        ]
        request = SearchRequest(query="demo")

        combined = backend._filter_and_score_results(results, request)

        assert combined[0]["score"] == pytest.approx(1.0)
        assert combined[1]["score"] == pytest.approx(
            0.5 * RETRIEVAL_PARAMS.CONFIG_FILE_SCORE_PENALTY
        )
