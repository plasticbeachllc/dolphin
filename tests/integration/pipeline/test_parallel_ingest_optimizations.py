"""Integration tests for Phase 2 performance optimizations.

Tests parallel scanning, parallel parsing, incremental embedding,
adaptive batching, and AST caching.
"""

import time
from pathlib import Path

import pytest

from kb.cache.ast_cache import ASTCache
from kb.chunkers.types import Chunk
from kb.embeddings.adaptive_batching import AdaptiveBatcher, create_adaptive_batches
from kb.hashing import hash_text
from kb.ingest.incremental import compute_chunk_diff
from kb.ingest.parallel_parser import ParallelChunkCache, ParseJob, ParseResult, parse_files_parallel
from kb.ingest.parallel_scanner import scan_repo_parallel
from kb.ingest.optimized_pipeline import OptimizedIngestionPipeline
from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.config import KBConfig
from kb.embeddings.provider import EmbeddingProvider


class TestParallelScanning:
    """Tests for parallel file scanning."""

    def test_parallel_scanning_small_repo(self, tmp_path):
        """Test parallel scanning on a small repository."""
        import subprocess

        # Create test repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Create test files
        for i in range(10):
            (repo_dir / f"file_{i}.py").write_text(f"# File {i}\nprint('hello')")

        # Add files to git
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)

        # Scan with parallel scanner
        candidates = scan_repo_parallel(repo_dir, [])

        assert len(candidates) == 10
        assert all(c.language == "python" for c in candidates)

    def test_parallel_vs_sequential_performance(self, tmp_path):
        """Compare parallel vs sequential scanning performance."""
        import subprocess

        from kb.ingest.scanner import scan_repo

        # Create larger test repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Create 100 test files
        for i in range(100):
            (repo_dir / f"file_{i}.py").write_text(f"# File {i}\n" + "x = 1\n" * 100)

        # Add files to git
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)

        # Sequential scan
        start = time.time()
        seq_candidates = scan_repo(repo_dir, [])
        seq_time = time.time() - start

        # Parallel scan
        start = time.time()
        par_candidates = scan_repo_parallel(repo_dir, [], num_workers=4)
        par_time = time.time() - start

        # Verify same results
        assert len(seq_candidates) == len(par_candidates)

        # Parallel should be faster (or at least not significantly slower)
        # Note: On small repos, parallel may have overhead
        print(f"Sequential: {seq_time:.3f}s, Parallel: {par_time:.3f}s")


class TestParallelParsing:
    """Tests for parallel tree-sitter parsing."""

    def test_parallel_parsing(self):
        """Test parallel parsing of multiple files."""
        jobs = [
            ParseJob(
                file_path=Path("test1.py"),
                content="def foo():\n    pass",
                language="python",
                model="small",
                token_target=400,
                overlap_pct=0.1,
            ),
            ParseJob(
                file_path=Path("test2.py"),
                content="def bar():\n    return 42",
                language="python",
                model="small",
                token_target=400,
                overlap_pct=0.1,
            ),
        ]

        results = parse_files_parallel(jobs, num_workers=2)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert all(len(r.chunks) > 0 for r in results)

    def test_chunk_cache(self):
        """Test ParallelChunkCache functionality."""
        cache = ParallelChunkCache(max_size=2)

        # Create test chunks
        chunks1 = [Chunk(text="chunk1", start_line=1, end_line=1, token_count=10)]
        chunks2 = [Chunk(text="chunk2", start_line=1, end_line=1, token_count=10)]

        # Put in cache
        cache.put("file1.py", "hash1", chunks1)
        cache.put("file2.py", "hash2", chunks2)

        # Retrieve
        assert cache.get("file1.py", "hash1") == chunks1
        assert cache.get("file2.py", "hash2") == chunks2

        # Cache miss
        assert cache.get("file3.py", "hash3") is None

        # Test eviction
        chunks3 = [Chunk(text="chunk3", start_line=1, end_line=1, token_count=10)]
        cache.put("file3.py", "hash3", chunks3)

        # file1 should be evicted (oldest)
        assert cache.size() == 2


class TestIncrementalEmbedding:
    """Tests for incremental embedding."""

    def test_compute_chunk_diff(self):
        """Test chunk diff computation."""
        # Existing chunks (by hash)
        existing_hashes = {
            hash_text("chunk1"),
            hash_text("chunk2"),
        }

        # New chunks
        new_chunks = [
            Chunk(text="chunk1", start_line=1, end_line=1, token_count=10),  # Unchanged
            Chunk(text="chunk2", start_line=2, end_line=2, token_count=10),  # Unchanged
            Chunk(text="chunk3", start_line=3, end_line=3, token_count=10),  # New
        ]

        diff = compute_chunk_diff(new_chunks, existing_hashes, "test_repo", "test.py")

        assert diff.stats["total_new"] == 3
        assert diff.stats["to_embed"] == 1  # Only chunk3
        assert diff.stats["unchanged"] == 2
        assert diff.stats["deleted"] == 0
        assert diff.stats["reuse_pct"] == 66  # 2/3

    def test_incremental_skip_unchanged(self):
        """Test that unchanged chunks are skipped."""
        new_chunks = [
            Chunk(text="unchanged", start_line=1, end_line=1, token_count=10),
        ]

        existing_hashes = {hash_text("unchanged")}

        diff = compute_chunk_diff(new_chunks, existing_hashes, "repo", "file.py")

        # Should skip all chunks
        assert len(diff.new_chunks) == 0
        assert diff.stats["reuse_pct"] == 100


class TestAdaptiveBatching:
    """Tests for adaptive batch sizing."""

    def test_adaptive_batcher_basic(self):
        """Test basic adaptive batching."""
        texts = [f"This is test text {i}" * 10 for i in range(100)]

        batcher = AdaptiveBatcher(
            target_tokens=1000,
            min_batch_size=5,
            max_batch_size=50,
        )
        batches = list(batcher.create_batches(texts))

        # Should create multiple batches
        assert len(batches) > 1
        assert len(batches) < 20  # Not too many

        # All texts should be included
        total_texts = sum(len(b) for b in batches)
        assert total_texts == len(texts)

    def test_adaptive_batching_respects_constraints(self):
        """Test that adaptive batching respects min/max constraints."""
        texts = ["short text"] * 100

        batcher = AdaptiveBatcher(
            target_tokens=10000,
            min_batch_size=10,
            max_batch_size=20,
        )

        batches = list(batcher.create_batches(texts))

        # All batches should respect constraints
        for batch in batches:
            assert len(batch) >= 10 or batch == batches[-1]  # Last batch may be smaller
            assert len(batch) <= 20

    def test_adaptive_batching_handles_large_chunks(self):
        """Test adaptive batching with large chunks."""
        # Create texts with varying sizes
        texts = [
            "short" * 10,  # ~50 tokens
            "medium" * 100,  # ~600 tokens
            "large" * 500,  # ~3000 tokens
        ]

        batches = create_adaptive_batches(
            texts,
            target_tokens=2000,
            min_batch_size=1,
            max_batch_size=100,
        )

        # Should create appropriate batches
        assert len(batches) > 0

        # Large chunk should be in its own batch or small batch
        for batch in batches:
            assert len(batch) >= 1


def test_optimized_pipeline_uses_repo_chunking_config(tmp_path, monkeypatch):
    """Ensure optimized pipeline respects repo chunking config."""
    import subprocess

    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    (repo_dir / "file1.py").write_text("def foo():\n    pass\n")
    (repo_dir / "file2.md").write_text("# Hello\nWorld\n")

    config_dir = repo_dir / ".dolphin"
    config_dir.mkdir()
    (config_dir / "chunking_config.toml").write_text(
        "\n".join(
            [
                "default_window_size = 600",
                "overlap_pct = 0.25",
                "",
                "[per_language]",
                "python = 123",
                "markdown = 321",
                "",
            ]
        )
    )

    captured_jobs = []

    def fake_parse_files_parallel(jobs, num_workers=None, pool=None):
        captured_jobs.extend(jobs)
        return [ParseResult(file_path=job.file_path, chunks=[], success=True) for job in jobs]

    monkeypatch.setattr("kb.ingest.optimized_pipeline.parse_files_parallel", fake_parse_files_parallel)

    store_root = tmp_path / "store"
    store_root.mkdir()
    metadata = SQLiteMetadataStore(store_root / "metadata.db")
    metadata.initialize()
    lancedb = LanceDBStore(store_root / "lancedb")
    lancedb.initialize_collections()

    class MockProvider(EmbeddingProvider):
        def embed_texts(self, model, texts):
            return [[0.1] * 1536 for _ in texts]

    config = KBConfig(
        store_root=store_root,
        embedding_provider="openai",
        openai_api_key_env="OPENAI_API_KEY",
    )

    pipeline = OptimizedIngestionPipeline(
        config=config,
        lancedb=lancedb,
        metadata=metadata,
        embedding_provider=MockProvider(),
        enable_parallel=True,
        enable_incremental=False,
        enable_ast_cache=False,
        num_workers=1,
    )

    pipeline.index_repository(repo_root=repo_dir, repo_name="test_repo", incremental=False)

    assert captured_jobs
    assert all(job.overlap_pct == 0.25 for job in captured_jobs)
    python_jobs = [job for job in captured_jobs if job.language == "python"]
    markdown_jobs = [job for job in captured_jobs if job.language == "markdown"]
    assert python_jobs
    assert markdown_jobs
    assert all(job.token_target == 123 for job in python_jobs)
    assert all(job.token_target == 321 for job in markdown_jobs)


class TestASTCache:
    """Tests for AST caching."""

    def test_ast_cache_basic(self):
        """Test basic AST cache operations."""
        cache = ASTCache(max_size=2)

        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]

        # Put and get
        cache.put("file.py", "hash1", chunks, "python")
        result = cache.get("file.py", "hash1")

        assert result == chunks

    def test_ast_cache_miss(self):
        """Test cache miss."""
        cache = ASTCache(max_size=2)

        result = cache.get("nonexistent.py", "hash")
        assert result is None

    def test_ast_cache_eviction(self):
        """Test LRU eviction."""
        cache = ASTCache(max_size=2)

        chunks1 = [Chunk(text="1", start_line=1, end_line=1, token_count=10)]
        chunks2 = [Chunk(text="2", start_line=1, end_line=1, token_count=10)]
        chunks3 = [Chunk(text="3", start_line=1, end_line=1, token_count=10)]

        cache.put("file1.py", "hash1", chunks1, "python")
        cache.put("file2.py", "hash2", chunks2, "python")
        cache.put("file3.py", "hash3", chunks3, "python")

        # file1 should be evicted
        assert cache.get("file1.py", "hash1") is None
        assert cache.get("file2.py", "hash2") == chunks2
        assert cache.get("file3.py", "hash3") == chunks3

    def test_ast_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        cache = ASTCache(max_size=10)

        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]
        cache.put("file.py", "hash", chunks, "python")

        # Generate hits and misses
        cache.get("file.py", "hash")  # Hit
        cache.get("file.py", "hash")  # Hit
        cache.get("other.py", "hash2")  # Miss
        cache.get("other.py", "hash2")  # Miss

        hit_rate = cache.hit_rate()
        assert hit_rate == 50.0  # 2 hits, 2 misses

    def test_ast_cache_invalidate(self):
        """Test cache invalidation for a file."""
        cache = ASTCache(max_size=10)

        chunks = [Chunk(text="test", start_line=1, end_line=1, token_count=10)]
        cache.put("file.py", "hash1", chunks, "python")
        cache.put("file.py", "hash2", chunks, "python")

        # Invalidate all versions of file.py
        cache.invalidate("file.py")

        assert cache.get("file.py", "hash1") is None
        assert cache.get("file.py", "hash2") is None


class TestPhase2Integration:
    """Integration tests combining multiple Phase 2 optimizations."""

    def test_full_optimized_pipeline(self, tmp_path):
        """Test full optimized pipeline with all Phase 2 features."""
        import subprocess

        # Create test repository
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Create test files
        for i in range(20):
            (repo_dir / f"module_{i}.py").write_text(f"# Module {i}\ndef function_{i}():\n    return {i}\n")

        # Add files to git
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)

        # Test 1: Parallel scanning
        candidates = scan_repo_parallel(repo_dir, [], num_workers=4)
        assert len(candidates) == 20

        # Test 2: Parallel parsing
        parse_jobs = []
        for candidate in candidates[:10]:  # Test subset
            with open(candidate.abs_path) as f:
                content = f.read()

            parse_jobs.append(
                ParseJob(
                    file_path=candidate.abs_path,
                    content=content,
                    language=candidate.language,
                    model="small",
                    token_target=400,
                    overlap_pct=0.1,
                )
            )

        results = parse_files_parallel(parse_jobs, num_workers=4)
        assert all(r.success for r in results)

        # Test 3: AST caching
        ast_cache = ASTCache(max_size=100)
        for result in results:
            if result.success:
                with open(result.file_path) as f:
                    content = f.read()
                content_hash = hash_text(content)
                ast_cache.put(str(result.file_path), content_hash, result.chunks, "python")

        # Verify cache works
        first_result = results[0]
        with open(first_result.file_path) as f:
            content = f.read()
        content_hash = hash_text(content)
        cached = ast_cache.get(str(first_result.file_path), content_hash)
        assert cached == first_result.chunks

        print(f"AST cache hit rate: {ast_cache.hit_rate()}%")
        print(f"AST cache stats: {ast_cache.stats()}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
