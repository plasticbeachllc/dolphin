"""Tests for helper method extraction."""

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest

from kb.config import KBConfig
from kb.embeddings.provider import EmbeddingProvider, set_default_provider
from kb.ingest.pipeline import IngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore


@pytest.fixture
def pipeline(tmp_path: Path) -> Generator[IngestionPipeline, None, None]:
    """Create a pipeline."""
    store_root = tmp_path / "store"
    store_root.mkdir()

    config = KBConfig(store_root=store_root, embedding_provider="openai", default_embed_model="small")
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
    # Reset provider
    set_default_provider(EmbeddingProvider())


@pytest.fixture
def repo(make_git_repo) -> Path:
    """Create a git repo with a Python file."""
    return make_git_repo(files={"file.py": "def f(): pass\n"})


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
        files_skipped_ignored,
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
