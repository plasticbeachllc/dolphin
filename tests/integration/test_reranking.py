import pytest
import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path

from kb.api.search_backend import create_search_backend
from kb.api.app import SearchRequest
from kb.ingest.pipeline import IngestionPipeline
from kb.chunkers.types import Chunk
from kb.retrieval.types import Document
from kb.config import KBConfig
from kb.store import LanceDBStore, SQLiteMetadataStore

def git_init_and_commit(path: Path):
    """Initialize a git repo and make an initial commit."""
    subprocess.check_call(["git", "init"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=path)
    subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=path)
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
        retrieval={
            "reranking": {"enabled": True, "model_name": "test-model"}
        }
    )
    
    lancedb = LanceDBStore(config.store_root)
    lancedb.initialize_collections()
    metadata = SQLiteMetadataStore(config.store_root / "metadata.db")
    metadata.initialize()

    metadata.record_repo("test_repo", str(tmp_path), default_embed_model="small")

    pipeline = IngestionPipeline(config, lancedb, metadata)
    
    dummy_chunks = [
        Chunk(
            text=f"dummy content {i}",
            start_line=i,
            end_line=i+1,
            token_count=len(f"dummy content {i}".split()),
        ) for i in range(2)
    ]
    # Create dummy files for the pipeline to find
    for i in range(2):
        (tmp_path / f"file_{i}.py").write_text(f"dummy content {i}")
        subprocess.check_call(["git", "add", f"file_{i}.py"], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-m", "Add dummy files"], cwd=tmp_path)
    
    # We need to mock the embedding provider
    with patch('kb.embeddings.provider.embed_texts_with_retry', return_value=[[0.1]*1536, [0.2]*1536]):
        pipeline.index(repo_name="test_repo", full_reindex=True)

    # Now, create the search backend using the pre-populated stores
    backend = create_search_backend(store_root=store_root, retrieval=config.retrieval)
    
    assert backend is not None, "Backend creation failed"
    assert backend.reranker is not None, "Reranker was not initialized"
    assert backend.reranker.enabled
    return backend

class TestRerankerIntegration:
    def test_search_with_reranking_flow(self, rerank_backend):
        """Test that the reranker is called and correctly reorders results."""
        initial_hits = [
            Document(chunk_id = "doc_0", score = 0.8, content = "dummy content 0"),
            Document(chunk_id = "doc_1", score = 0.7, content = "dummy content 1")
        ]
        
        rerank_backend.reranker.model.predict = MagicMock(return_value=[0.1, 0.9])

        with patch.object(rerank_backend, '_hybrid_search', return_value=initial_hits):
            request = SearchRequest(query="test", top_k=2)
            final_results = rerank_backend.search(request)

            rerank_backend.reranker.model.predict.assert_called_once()
            
            call_args = rerank_backend.reranker.model.predict.call_args[0][0]
            assert len(call_args) == 2
            assert call_args[0] == ["test", "dummy content 0"]
            assert call_args[1] == ["test", "dummy content 1"]

            assert len(final_results) == 2
            assert final_results[0]["chunk_id"] != "doc_0" # Check that it's not the original first
            assert "rerank_score" in final_results[0]