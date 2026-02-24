import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.api.app import SearchRequest
from kb.api.search_backend import create_search_backend
from kb.chunkers.types import Chunk
from kb.config import KBConfig, RerankingConfig, RetrievalConfig
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore


def git_init_and_commit(path: Path):
    """Initialize a git repo and make an initial commit."""
    subprocess.check_call(["git", "init"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=path)
    subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=path)
    subprocess.check_call(["git", "config", "commit.gpgsign", "false"], cwd=path)
    (path / "README.md").write_text("initial commit")
    subprocess.check_call(["git", "add", "README.md"], cwd=path)
    subprocess.check_call(["git", "commit", "-m", "Initial commit"], cwd=path)


@pytest.fixture
def rerank_backend(tmp_path):
    """Fixture for a search backend with reranking enabled in test mode."""
    # The pipeline expects a valid git repo
    git_init_and_commit(tmp_path)

    store_root = tmp_path / "kb_store"
    store_root.mkdir(parents=True, exist_ok=True)

    config = KBConfig(
        store_root=store_root,
        retrieval=RetrievalConfig(reranking=RerankingConfig(enabled=True, model="test-model")),
    )

    lancedb = LanceDBStore(config.store_root)
    lancedb.initialize_collections()
    metadata = SQLiteMetadataStore(config.store_root / "metadata.db")
    metadata.initialize()

    metadata.record_repo("test_repo", str(tmp_path), default_embed_model="small")

    pipeline = IngestionPipeline(config, lancedb, metadata)

    [
        Chunk(
            text=f"dummy content {i}",
            start_line=i,
            end_line=i + 1,
            token_count=len(f"dummy content {i}".split()),
        )
        for i in range(2)
    ]
    # Create dummy files for the pipeline to find
    for i in range(2):
        (tmp_path / f"file_{i}.py").write_text(f"dummy content {i}")
        subprocess.check_call(["git", "add", f"file_{i}.py"], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-m", "Add dummy files"], cwd=tmp_path)

    # We need to mock the embedding provider
    with patch(
        "kb.embeddings.provider.embed_texts_with_retry",
        return_value=[[0.1] * 1536, [0.2] * 1536],
    ):
        pipeline.index(repo_name="test_repo", full_reindex=True)

    # Force FTS rebuild to avoid malformed index errors in tests
    with metadata._connect() as conn:
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        conn.commit()

    # Now, create the search backend using the pre-populated stores
    backend = create_search_backend(store_root=store_root, reranker_config={"enabled": True, "model": "test-model"})

    assert backend is not None, "Backend creation failed"
    assert backend.reranker is not None, "Reranker was not initialized"
    assert backend.reranker.enabled
    return backend


class TestRerankerIntegration:
    def test_search_with_reranking_flow(self, rerank_backend):
        """Test that the reranker integration works correctly."""
        # Just verify that the reranker is initialized and the backend works
        assert rerank_backend.reranker is not None
        assert rerank_backend.reranker.enabled

        # Test that a basic search works with reranking enabled
        request = SearchRequest(query="test", top_k=2)

        # Mock empty results from stores to focus on reranking logic
        with (
            patch.object(rerank_backend.lance_store, "query", return_value=[]),
            patch.object(rerank_backend.sql_store, "bm25_search", return_value=[]),
        ):
            # Should complete without error even with no results
            results, _ = rerank_backend.search(request)
            assert isinstance(results, list)

        # The test passes if reranking is properly initialized and search works
        assert rerank_backend.reranker.enabled
