"""Tests for dynamic batch sizing."""

import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kb.config import KBConfig
from kb.embeddings.provider import set_default_provider
from kb.ingest.dynamic_pool import WorkloadEstimator
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore


@pytest.fixture
def pipeline(tmp_path: Path) -> IngestionPipeline:
    """Create a pipeline."""
    store_root = tmp_path / "store"
    store_root.mkdir()

    config = KBConfig(store_root=store_root, embedding_provider="openai")
    metadata = SQLiteMetadataStore(store_root / "metadata.db")
    metadata.initialize()
    lancedb = LanceDBStore(store_root / "lancedb")
    lancedb.initialize_collections()

    class MockProvider:
        def embed_texts(self, model, texts):
            return [[0.1] * 1536 for _ in texts]

        async def embed_texts_async(self, model, texts):
            await asyncio.sleep(0.01)
            return [[0.1] * 1536 for _ in texts]

    set_default_provider(MockProvider())
    return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)


@pytest.fixture
def repo_with_files(tmp_path: Path) -> Path:
    """Create repo with multiple files."""
    import subprocess

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

    for i in range(10):
        (repo_path / f"file{i}.py").write_text(f"def f{i}(): pass\n")

    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Init"], cwd=repo_path, check=True, capture_output=True)

    return repo_path


def test_workload_estimator_calculations():
    """Test WorkloadEstimator batch size logic."""
    estimator = WorkloadEstimator()

    # Small workload
    batch_size = estimator.estimate_batch_size(total_items=20, worker_count=2, min_batch=10, max_batch=100)
    assert 10 <= batch_size <= 100

    # Large workload
    batch_size = estimator.estimate_batch_size(total_items=500, worker_count=8, min_batch=10, max_batch=100)
    assert 10 <= batch_size <= 100

    # Edge case: very few items
    batch_size = estimator.estimate_batch_size(total_items=5, worker_count=4, min_batch=10, max_batch=100)
    assert batch_size == 10  # Clamped to min


@pytest.mark.asyncio
async def test_dynamic_batch_sizing_used(pipeline, repo_with_files):
    """Verify WorkloadEstimator is used for batch sizing."""

    pipeline.metadata.record_repo(name="test_repo", path=repo_with_files, default_embed_model="small")

    with patch("kb.ingest.pipeline.WorkloadEstimator") as MockEstimator:
        mock_instance = Mock()
        mock_instance.estimate_batch_size.return_value = 25
        MockEstimator.return_value = mock_instance

        await pipeline.index_parallel("test_repo", dry_run=False, full_reindex=True, max_workers=2)

        # Verify it was called
        MockEstimator.assert_called_once()
        mock_instance.estimate_batch_size.assert_called()

        # Check parameters
        call_args = mock_instance.estimate_batch_size.call_args
        assert call_args.kwargs["total_items"] == 10
        assert call_args.kwargs["worker_count"] > 0
        print(f"✓ Dynamic batch sizing verified with {call_args.kwargs['worker_count']} workers")
