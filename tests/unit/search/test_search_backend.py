from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kb.api.app import SearchRequest
from kb.api.search_backend import KnowledgeSearchBackend, create_search_backend
from kb.config import KBConfig
from kb.retrieval.bm25_normalizer import SigmoidNormalizer
from kb.retrieval.bm25_stats import BM25Statistics


@pytest.fixture
def mock_providers():
    """Provides mock stores and providers for the search backend."""
    embedding_provider = MagicMock(spec=["embed_texts"])
    lance_store = MagicMock(spec=["query", "upsert_chunks"])
    sql_store = MagicMock(
        spec=[
            "bm25_search",
            "get_chunk_contents",
            "get_chunk_by_id",
            "get_chunk_by_content_identity",
            "get_repo_by_name",
            "get_file_id",
            "index_chunk_for_fts",
            "configure_bm25_statistics",
        ]
    )
    return embedding_provider, lance_store, sql_store


@pytest.fixture
def basic_backend(mock_providers):
    """A basic backend with hybrid search enabled."""
    embedding_provider, lance_store, sql_store = mock_providers
    return KnowledgeSearchBackend(embedding_provider, lance_store, sql_store, hybrid_search_enabled=True)


class TestKnowledgeSearchBackend:
    def test_search_basic_hybrid(self, basic_backend):
        """Test that hybrid search correctly fuses vector and BM25 results."""
        embedding_provider, lance_store, sql_store = (
            basic_backend.embedding_provider,
            basic_backend.lance_store,
            basic_backend.sql_store,
        )

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        lance_store.query.return_value = [{"id": "chunk1", "_distance": 0.2, "repo": "test", "path": "p1.py"}]
        # `reciprocal_rank_fusion` expects the `id_field` to be 'chunk_id'
        sql_store.bm25_search.return_value = [
            {
                "chunk_id": "chunk2",
                "score": 25.0,
                "repo": "test",
                "path": "p2.py",
                "text_hash": "hash2",
            }
        ]
        # Mock the hydration methods for the BM25 result
        sql_store.get_repo_by_name.return_value = {"id": 1}
        sql_store.get_file_id.return_value = 2
        sql_store.get_chunk_by_content_identity.return_value = {
            "path": "p2.py",
            "chunk_id": "chunk2",
            "start_line": 1,
            "end_line": 10,
        }

        request = SearchRequest(query="test", top_k=10)
        results = basic_backend.search(request)

        assert len(results) == 2
        assert {r["chunk_id"] for r in results} == {"chunk1", "chunk2"}
        assert "score" in results[0]
        assert results[0]["score"] > 0

    def test_search_with_score_cutoff(self, basic_backend):
        """Test that the score_cutoff is applied after RRF fusion."""
        embedding_provider, lance_store, sql_store = (
            basic_backend.embedding_provider,
            basic_backend.lance_store,
            basic_backend.sql_store,
        )

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        # Vector search result will rank at position 1, giving RRF score ~0.016
        lance_store.query.return_value = [{"id": "chunk1", "_distance": 0.1, "repo": "repo", "path": "test.py"}]
        # BM25 result will rank at position 2, giving RRF score ~0.016 (similar rank)
        sql_store.bm25_search.return_value = [
            {
                "chunk_id": "chunk2",
                "score": 5.0,
                "repo": "repo",
                "path": "test.py",
                "text_hash": "hash2",
            }
        ]
        # Mock the hydration methods for the BM25 result
        sql_store.get_repo_by_name.return_value = {"id": 1}
        sql_store.get_file_id.return_value = 2
        sql_store.get_chunk_by_content_identity.return_value = {
            "path": "test.py",
            "chunk_id": "chunk2",
            "start_line": 1,
            "end_line": 10,
        }

        # Use low cutoff (0.0) to accept RRF scores (~0.016)
        request = SearchRequest(query="test", score_cutoff=0.0)
        results = basic_backend.search(request)

        assert len(results) == 2  # Both should pass with RRF scores

        # Test high cutoff that filters out results
        request_high_cutoff = SearchRequest(query="test", score_cutoff=0.5)
        results_high = basic_backend.search(request_high_cutoff)

        # RRF scores (~0.016) should be below 0.5 cutoff, so no results
        assert len(results_high) == 0

    def test_hydrate_bm25_results_with_deterministic_ids(self, basic_backend):
        _embedding_provider, _lance_store, sql_store = (
            basic_backend.embedding_provider,
            basic_backend.lance_store,
            basic_backend.sql_store,
        )

        # Mock the new lookup methods
        sql_store.get_repo_by_name = MagicMock(return_value={"id": 1})
        sql_store.get_file_id = MagicMock(return_value=2)

        deterministic_id = "32char_deterministic_hash_id"
        sql_store.get_chunk_by_content_identity.return_value = {
            "chunk_id": "uuid-123",
            "text_hash": "abcdef",
            "embed_model": "small",
            "path": "repo/file.py",
            "language": "python",
            "start_line": 10,
            "end_line": 20,
            "symbol_name": "func",
            "symbol_path": "module.func",
        }
        sql_store.get_chunk_by_id.return_value = None

        hydrated = basic_backend._hydrate_bm25_results(
            [
                {
                    "chunk_id": deterministic_id,
                    "repo": "repo",
                    "path": "repo/file.py",
                    "text_hash": "abcdef",  # Now includes text_hash from BM25 search
                    "score": 5.0,
                }
            ],
            sql_store,
        )

        # Verify the new lookup flow was used
        sql_store.get_repo_by_name.assert_called_once_with("repo")
        sql_store.get_file_id.assert_called_once_with(1, "repo/file.py")
        sql_store.get_chunk_by_content_identity.assert_called_once_with(1, 2, "abcdef")
        sql_store.get_chunk_by_id.assert_not_called()
        assert hydrated[0]["start_line"] == 10
        assert hydrated[0]["chunk_id"] == deterministic_id

    def test_bm25_normalization_uses_min_max_when_stats_available(self, tmp_path: Path):
        stats_path = tmp_path / "bm25_stats.json"
        stats = BM25Statistics(
            min_score=0.0,
            max_score=40.0,
            mean=10.0,
            median=8.0,
            std=2.5,
            p05=1.0,
            p25=5.0,
            p75=12.0,
            p95=20.0,
            p99=30.0,
            sample_size=200,
        )
        stats.save(stats_path)
        config = KBConfig.from_mapping(
            {
                "storage": {"store_root": str(tmp_path)},
                "retrieval": {"bm25_normalization": {"strategy": "min_max", "stats_path": str(stats_path)}},
            }
        )
        embedding_provider = MagicMock()
        lance_store = MagicMock()
        sql_store = MagicMock(spec=["configure_bm25_statistics"])
        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store, config=config)

        normalized = backend._normalize_bm25_score(20.0)

        assert normalized == pytest.approx(0.5, rel=1e-3)
        sql_store.configure_bm25_statistics.assert_called_once()

    def test_bm25_normalization_falls_back_without_stats(self, tmp_path: Path):
        missing_path = tmp_path / "absent_stats.json"
        config = KBConfig.from_mapping(
            {
                "storage": {"store_root": str(tmp_path)},
                "retrieval": {"bm25_normalization": {"strategy": "min_max", "stats_path": str(missing_path)}},
            }
        )
        embedding_provider = MagicMock()
        lance_store = MagicMock()
        sql_store = MagicMock(spec=["configure_bm25_statistics"])
        backend = KnowledgeSearchBackend(embedding_provider, lance_store, sql_store, config=config)

        value = 12.0
        normalized = backend._normalize_bm25_score(value)
        expected = SigmoidNormalizer().normalize(value)

        assert normalized == pytest.approx(expected, rel=1e-6)

    def test_graph_config_applied_to_enricher(self, mock_providers):
        embedding_provider, lance_store, sql_store = mock_providers
        graph_store = MagicMock()
        config = KBConfig.from_mapping({"graph": {"max_related_nodes": 2, "max_edges_per_node": 1}})

        with patch("kb.api.search_backend.GraphContextEnricher") as mock_enricher:
            KnowledgeSearchBackend(
                embedding_provider,
                lance_store,
                sql_store,
                config=config,
                graph_store=graph_store,
            )

            mock_enricher.assert_called_once_with(
                graph_store=graph_store,
                sql_store=sql_store,
                max_related_nodes=2,
                max_edges_per_node=1,
            )


@pytest.fixture
def real_backend(tmp_path: Path):
    """Provides a backend with real stores for integration testing."""
    backend = create_search_backend(store_root=tmp_path, embedding_provider_type="stub")

    # Initialize database to ensure tables exist
    backend.sql_store.initialize()

    # Cleanup: Clear any existing test data from previous runs
    with backend.sql_store._connect() as conn:
        cur = conn.cursor()
        # Clear FTS5 table (best effort — some environments disallow writes)
        try:
            cur.execute("DELETE FROM chunks_fts")
        except Exception:
            pass
        conn.commit()

    # Clear LanceDB tables for both models
    try:
        # Delete any existing tables in LanceDB
        import shutil

        lance_path = tmp_path / "lancedb"
        if lance_path.exists():
            # Remove tables for small and large models
            for model_dir in lance_path.glob("*"):
                if model_dir.is_dir():
                    shutil.rmtree(model_dir, ignore_errors=True)
    except Exception:
        pass  # Best effort cleanup

    yield backend

    # Post-test cleanup to ensure no data persists
    try:
        with backend.sql_store._connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM chunks_fts")
            except Exception:
                pass
            conn.commit()
    except Exception:
        pass  # Best effort cleanup


class TestSearchBackendIntegration:
    def test_end_to_end_search_flow(self, real_backend: KnowledgeSearchBackend):
        """Test a full search cycle from indexing to retrieval."""
        import logging

        # Database is already initialized and cleaned by the fixture

        # Create test content and compute its hash
        test_content = "some test content"
        from kb.hashing import hash_text

        text_hash = hash_text(test_content)

        # Use production-format chunk ID with computed hash: repo_id:file_id:embed_model:text_hash:start_line:end_line
        chunk_id = f"10:617:small:{text_hash}:2:3"

        logging.info(f"Test: Creating chunk with ID: {chunk_id}")
        logging.info(f"Test: Content hash: {text_hash}")

        chunks_to_upsert = [
            {
                "id": chunk_id,
                "vector": [0.1] * 1536,
                "repo": "test-repo",
                "path": "test.py",
            }
        ]
        real_backend.lance_store.upsert_chunks("test-repo", chunks_to_upsert, model="small")
        real_backend.sql_store.index_chunk_for_fts(
            content_id=chunk_id,
            repo="test-repo",
            path="test.py",
            content=test_content,
            text_hash=text_hash,
        )

        # Verify FTS indexing worked
        with real_backend.sql_store._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT content_id, content FROM chunks_fts WHERE repo = 'test-repo'")
            fts_rows = cur.fetchall()
            logging.info(f"Test: FTS entries after indexing: {len(fts_rows)}")
            for row in fts_rows:
                logging.info(f"  FTS content_id: {row[0]}, content: {row[1][:50]}...")

        request = SearchRequest(query="test", top_k=5, embed_model="small")
        results = real_backend.search(request)

        logging.info(f"Test: Search returned {len(results)} results")
        for i, result in enumerate(results):
            logging.info(
                f"  Result {i}: chunk_id={result.get('chunk_id')}, "
                f"score={result.get('score')}, repo={result.get('repo')}, path={result.get('path')}"
            )

        assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"
        assert "score" in results[0], f"Result missing 'score' field: {results[0]}"
        # Expect the production-format chunk ID
        assert results[0]["chunk_id"] == chunk_id, f"Expected chunk_id {chunk_id}, got {results[0]['chunk_id']}"
