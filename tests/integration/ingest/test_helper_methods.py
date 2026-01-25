"""Tests for helper method extraction."""

import asyncio
from pathlib import Path

import pytest

from kb.config import KBConfig
from kb.embeddings.provider import EmbeddingProvider, set_default_provider
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

    class MockProvider(EmbeddingProvider):
        def embed_texts(self, model, texts):
            return [[0.1] * 1536 for _ in texts]

        async def embed_texts_async(self, model, texts):
            await asyncio.sleep(0.01)
            return [[0.1] * 1536 for _ in texts]

    set_default_provider(MockProvider())
    return IngestionPipeline(config=config, lancedb=lancedb, metadata=metadata)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a git repo."""
    import subprocess

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

    (repo_path / "file.py").write_text("def f(): pass\n")

    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Init"], cwd=repo_path, check=True, capture_output=True)

    return repo_path


def test_setup_parallel_session_helper_exists(pipeline, repo):
    """Verify _setup_parallel_session helper method exists and works."""

    pipeline.metadata.record_repo(name="test_repo", path=repo, default_embed_model="small")

    # Call helper directly
    result = pipeline._setup_parallel_session(
        repo_name="test_repo", force=False, full_reindex=True, dry_run=False, max_workers=2
    )

    # Unpack and verify
    (
        repo_id,
        root,
        embed_model,
        commit_sha,
        branch,
        session_id,
        error_logger,
        ignore_patterns,
        changed_files,
        deleted_files,
    ) = result

    assert repo_id > 0
    assert root == repo
    assert embed_model == "small"
    assert commit_sha
    assert branch
    assert session_id
    assert error_logger is not None
    assert isinstance(ignore_patterns, set)
    assert len(changed_files) == 1  # One file
    assert len(deleted_files) == 0
    print(f"✓ Helper method verified: returned {len(result)} components")
