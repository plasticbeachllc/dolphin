import threading
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
            "get_chunk_locations_by_identity",
            "get_bm25_hydration_map",
            "get_repo_by_name",
            "get_file_id",
            "index_chunk_for_fts",
            "configure_bm25_statistics",
        ]
    )
    return embedding_provider, lance_store, sql_store


@pytest.fixture
def basic_backend(mock_providers, tmp_path):
    """A basic backend with hybrid search enabled."""
    embedding_provider, lance_store, sql_store = mock_providers
    config = KBConfig.from_mapping(
        {"storage": {"store_root": str(tmp_path)}, "embedding": {"default_embed_model": "small"}}
    )
    return KnowledgeSearchBackend(embedding_provider, lance_store, sql_store, hybrid_search_enabled=True, config=config)


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
        sql_store.get_bm25_hydration_map.return_value = {
            "chunk2": {
                "repo_id": 1,
                "file_id": 2,
                "text_hash": "hash2",
                "embed_model": "small",
                "locations": [
                    {
                        "start_line": 1,
                        "end_line": 10,
                        "symbol_kind": None,
                        "symbol_name": None,
                        "symbol_path": None,
                    }
                ],
            }
        }

        request = SearchRequest(query="test", top_k=10)
        results, _ = basic_backend.search(request)

        expected_bm25_id = "1:2:small:hash2:1:10"
        assert len(results) == 2
        assert {r["chunk_id"] for r in results} == {"chunk1", expected_bm25_id}
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
        sql_store.get_bm25_hydration_map.return_value = {
            "chunk2": {
                "repo_id": 1,
                "file_id": 2,
                "text_hash": "hash2",
                "embed_model": "small",
                "locations": [
                    {
                        "start_line": 1,
                        "end_line": 10,
                        "symbol_kind": None,
                        "symbol_name": None,
                        "symbol_path": None,
                    }
                ],
            }
        }

        # Use low cutoff (0.0) to accept RRF scores (~0.016)
        request = SearchRequest(query="test", score_cutoff=0.0)
        results, _ = basic_backend.search(request)

        assert len(results) == 2  # Both should pass with RRF scores

        # Test high cutoff that filters out results
        request_high_cutoff = SearchRequest(query="test", score_cutoff=0.5)
        results_high, _ = basic_backend.search(request_high_cutoff)

        # RRF scores (~0.016) should be below 0.5 cutoff, so no results
        assert len(results_high) == 0

    def test_hydrate_bm25_results_with_deterministic_ids(self, basic_backend):
        _embedding_provider, _lance_store, sql_store = (
            basic_backend.embedding_provider,
            basic_backend.lance_store,
            basic_backend.sql_store,
        )

        deterministic_id = "32char_deterministic_hash_id"
        sql_store.get_bm25_hydration_map.return_value = {
            deterministic_id: {
                "repo_id": 1,
                "file_id": 2,
                "text_hash": "abcdef",
                "embed_model": "small",
                "locations": [
                    {
                        "start_line": 10,
                        "end_line": 20,
                        "symbol_kind": None,
                        "symbol_name": "func",
                        "symbol_path": "module.func",
                    }
                ],
            }
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
            embed_model="small",
        )

        # Verify bulk hydration path was used
        sql_store.get_bm25_hydration_map.assert_called_once_with([deterministic_id], "small")
        sql_store.get_chunk_by_id.assert_not_called()
        assert hydrated[0]["start_line"] == 10
        # Check generated ID format: {repo_id}:{file_id}:{embed_model}:{text_hash}:{start_line}:{end_line}
        expected_id = "1:2:small:abcdef:10:20"
        assert hydrated[0]["chunk_id"] == expected_id

    def test_search_executes_vector_and_bm25_in_parallel(self, mock_providers, tmp_path: Path):
        embedding_provider, lance_store, sql_store = mock_providers
        config = KBConfig.from_mapping(
            {"storage": {"store_root": str(tmp_path)}, "embedding": {"default_embed_model": "small"}}
        )
        backend = KnowledgeSearchBackend(
            embedding_provider,
            lance_store,
            sql_store,
            hybrid_search_enabled=True,
            config=config,
        )

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]

        bm25_started = threading.Event()

        def vector_query(*args, **kwargs):
            assert bm25_started.wait(timeout=0.5), "BM25 search did not start concurrently"
            return [{"id": "chunk1", "_distance": 0.1, "repo": "repo", "path": "file.py"}]

        def bm25_search(*args, **kwargs):
            bm25_started.set()
            return []

        lance_store.query.side_effect = vector_query
        sql_store.bm25_search.side_effect = bm25_search
        sql_store.get_bm25_hydration_map.return_value = {}

        results, _ = backend.search(SearchRequest(query="parallel check", top_k=5))

        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk1"

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

    def test_search_pagination_flow(self, basic_backend):
        """Test cursor-based pagination flow."""
        embedding_provider, lance_store, sql_store = (
            basic_backend.embedding_provider,
            basic_backend.lance_store,
            basic_backend.sql_store,
        )

        embedding_provider.embed_texts.return_value = [[0.1] * 1536]

        # Create 20 mock results with decreasing scores
        all_results = []
        for i in range(20):
            all_results.append(
                {
                    "id": f"chunk_{i}",
                    "_distance": 0.1 * (i + 1),  # Increasing distance -> decreasing score
                    "repo": "repo",
                    "path": f"file_{i}.py",
                }
            )

        # Mock lance store to return ALL results initially (simulating candidate pool)
        # In real backend, we rely on candidate_multiplier, but here we just mock the return
        lance_store.query.return_value = all_results

        sql_store.bm25_search.return_value = []  # vector only for simplicity

        # Page 1: Top 5
        request = SearchRequest(query="test", top_k=5)
        results, next_cursor = basic_backend.search(request)

        assert len(results) == 5
        assert next_cursor is not None
        assert results[0]["chunk_id"] == "chunk_0"
        assert results[4]["chunk_id"] == "chunk_4"

        # Page 2: Next 5 using cursor
        request_page_2 = SearchRequest(query="test", top_k=5, cursor=next_cursor)
        results_2, next_cursor_2 = basic_backend.search(request_page_2)

        assert len(results_2) == 5
        assert next_cursor_2 is not None
        assert results_2[0]["chunk_id"] == "chunk_5"

        # Page 3: Next 5 using cursor 2
        request_page_3 = SearchRequest(query="test", top_k=5, cursor=next_cursor_2)
        results_3, next_cursor_3 = basic_backend.search(request_page_3)

        assert len(results_3) == 5
        assert next_cursor_3 is not None
        assert results_3[0]["chunk_id"] == "chunk_10"

        # Page 4: Verify distinctness from Page 1
        page1_ids = {r["chunk_id"] for r in results}
        page2_ids = {r["chunk_id"] for r in results_2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_search_cursor_integrity(self, basic_backend):
        """Test invalid cursor handling."""
        embedding_provider, lance_store, _sql_store = (
            basic_backend.embedding_provider,
            basic_backend.lance_store,
            basic_backend.sql_store,
        )
        embedding_provider.embed_texts.return_value = [[0.1] * 1536]
        lance_store.query.return_value = [{"id": "c1", "_distance": 0.1, "repo": "r", "path": "p"}]

        # Case 1: Tampered/Invalid Base64
        request = SearchRequest(query="test", top_k=5, cursor="invalid_base64!@#")
        # Should log warning and treat as no cursor (return page 1)
        results, _ = basic_backend.search(request)
        assert len(results) == 1

        # Case 2: Query mismatch (cursor from "test", request for "other")
        # Generate valid cursor for "test"
        valid_cursor = basic_backend._encode_cursor("test", 0.9, "c1")

        request_mismatch = SearchRequest(query="other", top_k=5, cursor=valid_cursor)
        # Should detect hash mismatch and ignore cursor
        results_mismatch, _ = basic_backend.search(request_mismatch)
        assert len(results_mismatch) == 1


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

        request = SearchRequest(query="test", top_k=5)
        results, _ = real_backend.search(request)

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
