"""Tests for FTS indexing in parallel mode."""

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest

from kb.config import KBConfig
from kb.embeddings.provider import EmbeddingProvider, set_default_provider
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore


@pytest.fixture
def pipeline_with_fts(tmp_path: Path) -> Generator[IngestionPipeline, None, None]:
    """Create a pipeline for FTS testing."""
    store_root = tmp_path / "store"
    store_root.mkdir()

    config = KBConfig(store_root=store_root, embedding_provider="openai")
    metadata = SQLiteMetadataStore(store_root / "metadata.db")
    metadata.initialize()

    lancedb = LanceDBStore(store_root / "lancedb")
    lancedb.initialize_collections()

    class MockProvider(EmbeddingProvider):
        def embed_texts(self, model, texts):
            return [[0.1] * 1536 for _ in texts]

        async def embed_texts_async(self, model, texts):
            await asyncio.sleep(0.01)
            return [[0.1] * 1536 for _ in texts]

    set_default_provider(MockProvider())
    yield IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)
    # Reset default provider to stub
    set_default_provider(EmbeddingProvider())


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a sample git repo."""
    import subprocess

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

    for i in range(5):
        (repo_path / f"file{i}.py").write_text(f"def func{i}(): pass\n")

    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)

    return repo_path


@pytest.mark.asyncio
async def test_fts_indexing_called_in_parallel_mode(pipeline_with_fts, sample_repo):
    """Verify that FTS chunks are indexed during parallel indexing."""

    pipeline_with_fts.metadata.record_repo(name="test_repo", path=sample_repo, default_embed_model="small")

    # Spy on FTS indexing
    original_bulk_index = pipeline_with_fts.metadata.bulk_index_chunks_for_fts
    fts_calls = []

    def spy_bulk_index(chunks):
        fts_calls.append(len(chunks))
        return original_bulk_index(chunks)

    pipeline_with_fts.metadata.bulk_index_chunks_for_fts = spy_bulk_index

    # Run parallel index
    result = await pipeline_with_fts.index_parallel("test_repo", dry_run=False, full_reindex=True, max_workers=2)

    # Verify FTS was called
    assert len(fts_calls) > 0, "FTS indexing should be called"
    assert sum(fts_calls) > 0, "FTS chunks should be indexed"
    assert result["chunks_indexed"] > 0
    print(f"✓ FTS verified: {len(fts_calls)} calls, {sum(fts_calls)} total chunks")
