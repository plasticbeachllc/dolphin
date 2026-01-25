"""Integration tests for parallel indexing workflow."""

import pytest
import asyncio
from pathlib import Path
from typing import Generator

from kb.ingest.pipeline import IngestionPipeline
from kb.config import KBConfig
from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.embeddings.provider import create_provider, set_default_provider

@pytest.fixture
def mock_pipeline(tmp_path: Path) -> IngestionPipeline:
    """Create a pipeline with mocked storage."""
    store_root = tmp_path / "store"
    store_root.mkdir()
    
    config = KBConfig(
        store_root=str(store_root),
        embedding_provider="openai",  # Will need mock
        openai_api_key_env="OPENAI_API_KEY",
    )
    
    # Initialize stores
    metadata = SQLiteMetadataStore(store_root / "metadata.db")
    metadata.initialize()
    
    lancedb = LanceDBStore(store_root / "lancedb")
    lancedb.initialize_collections()
    
    # Mock Provider
    class MockProvider:
        def embed_texts(self, model, texts):
            # Return dummy vectors
            return [[0.1] * 1536 for _ in texts]
            
        async def embed_texts_async(self, model, texts):
            await asyncio.sleep(0.01) # Simulate network
            return [[0.1] * 1536 for _ in texts]

    set_default_provider(MockProvider())
    
    return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)

@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a sample git repo."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    
    # Init git
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
    
    # Add files
    (repo_path / "file1.py").write_text("def foo():\n    pass\n")
    (repo_path / "file2.md").write_text("# Hello\nWorld\n")
    
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
    
    return repo_path

@pytest.mark.asyncio
async def test_parallel_indexing_execution(mock_pipeline, sample_repo):
    """Test that parallel indexing runs without error and produces results."""
    
    # Register repo
    mock_pipeline.metadata.record_repo(name="test_repo", path=sample_repo, default_embed_model="small")
    
    # Run parallel index
    result = await mock_pipeline.index_parallel(
        "test_repo",
        dry_run=False,
        full_reindex=True,
        max_workers=2
    )
    
    assert result["files_indexed"] == 2
    assert result["chunks_indexed"] > 0
    assert result["vectors_written"] > 0
    assert result["session_id"] is not None
    
    # Verify metadata persistence
    repo = mock_pipeline.metadata.get_repo_by_name("test_repo")
    files = mock_pipeline.metadata.get_all_files_for_repo(repo["id"])
    assert len(files) == 2
    
    # Verify LanceDB persistence (mock check)
    # We can check vectors_written counter for now as proxy
    
@pytest.mark.asyncio
async def test_incremental_parallel_update(mock_pipeline, sample_repo):
    """Test incremental updates with parallel indexer."""
    
    mock_pipeline.metadata.record_repo(name="test_repo", path=sample_repo, default_embed_model="small")
    
    # Initial Index
    await mock_pipeline.index_parallel("test_repo", full_reindex=True, max_workers=2)
    
    # Modify file
    import subprocess
    (sample_repo / "file1.py").write_text("def foo():\n    print('changed')\n")
    subprocess.run(["git", "add", "."], cwd=sample_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Update"], cwd=sample_repo, check=True)
    
    # Incremental Index
    result = await mock_pipeline.index_parallel("test_repo", full_reindex=False, max_workers=2)
    
    assert result["files_indexed"] == 1
    assert result["chunks_indexed"] > 0
