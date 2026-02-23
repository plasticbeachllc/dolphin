"""Tests for negative filtering functionality in search backend."""

from typing import cast

from kb.api.app import SearchRequest
from kb.api.search_backend import KnowledgeSearchBackend
from kb.embeddings.provider import EmbeddingProvider
from kb.store.lancedb_store import LanceDBStore
from kb.store.sqlite_meta import SQLiteMetadataStore


class TestNegativeFiltering:
    """Test suite for exclude_paths and exclude_patterns filtering."""

    @staticmethod
    def _legacy_filter_then_score(results: list[dict[str, object]], request: SearchRequest) -> list[dict[str, object]]:
        """Reproduce the historical multi-pass filtering and scoring pipeline."""

        import fnmatch
        from pathlib import PurePosixPath

        def normalize_path(path_str: str) -> PurePosixPath:
            path_str = path_str.lstrip("./")
            path_str = path_str.lstrip("/")
            return PurePosixPath(path_str)

        filtered = results

        if request.repos:
            repo_set = set(request.repos)
            filtered = [r for r in filtered if r.get("repo") in repo_set]

        if request.path_prefix:

            def matches_prefix(path_str: str) -> bool:
                path = normalize_path(path_str)
                assert request.path_prefix is not None
                for prefix_str in request.path_prefix:
                    prefix = normalize_path(prefix_str)
                    try:
                        path.relative_to(prefix)
                        return True
                    except ValueError:
                        continue
                return False

            filtered = [r for r in filtered if matches_prefix(str(r.get("path", "")))]

        if request.exclude_paths:

            def matches_excluded_path(path_str: str) -> bool:
                path = normalize_path(path_str)
                assert request.exclude_paths is not None
                for excl_str in request.exclude_paths:
                    excl = normalize_path(excl_str)
                    try:
                        path.relative_to(excl)
                        return True
                    except ValueError:
                        continue
                return False

            filtered = [r for r in filtered if not matches_excluded_path(str(r.get("path", "")))]

        if request.exclude_patterns:
            assert request.exclude_patterns is not None
            exclude_patterns = request.exclude_patterns

            def matches_excluded_pattern(path_str: str) -> bool:
                path = normalize_path(path_str)
                for pattern in exclude_patterns:
                    if fnmatch.fnmatch(str(path), pattern) or fnmatch.fnmatch(path.name, pattern):
                        return True
                return False

            filtered = [r for r in filtered if not matches_excluded_pattern(str(r.get("path", "")))]

        return filtered

    def test_exclude_paths_single_path(self):
        """Test excluding a single path prefix."""
        # Mock results with various paths
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {
                "chunk_id": "2",
                "repo": "test",
                "path": "tests/test_main.py",
                "score": 0.8,
            },
            {"chunk_id": "3", "repo": "test", "path": "src/utils.py", "score": 0.7},
            {"chunk_id": "4", "repo": "test", "path": "docs/guide.md", "score": 0.6},
        ]

        request = SearchRequest(query="test", exclude_paths=["tests/"])

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should exclude tests/ directory
        assert len(filtered) == 3
        assert all(isinstance(r["path"], str) and not r["path"].startswith("tests/") for r in filtered)
        assert any(r["path"] == "src/main.py" for r in filtered)
        assert any(r["path"] == "src/utils.py" for r in filtered)
        assert any(r["path"] == "docs/guide.md" for r in filtered)

    def test_exclude_paths_multiple_paths(self):
        """Test excluding multiple path prefixes."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {
                "chunk_id": "2",
                "repo": "test",
                "path": "tests/test_main.py",
                "score": 0.8,
            },
            {
                "chunk_id": "3",
                "repo": "test",
                "path": "node_modules/lib.js",
                "score": 0.7,
            },
            {"chunk_id": "4", "repo": "test", "path": "dist/bundle.js", "score": 0.6},
            {"chunk_id": "5", "repo": "test", "path": "src/utils.py", "score": 0.5},
        ]

        request = SearchRequest(query="test", exclude_paths=["tests/", "node_modules/", "dist/"])

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        backend._filter_and_score_results(results, request)

    def test_filter_and_score_matches_legacy_pipeline(self):
        """Ensure the new single-pass helper matches the historical behavior."""

        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "tests/test_main.py", "score": 0.8},
            {"chunk_id": "3", "repo": "test", "path": "docs/guide.md", "score": 0.7},
            {"chunk_id": "4", "repo": "lib", "path": "src/lib.py", "score": 0.6},
            {"chunk_id": "5", "repo": "lib", "path": "config/settings.toml", "score": 0.5},
        ]

        request = SearchRequest(
            query="test",
            repos=["test"],
            path_prefix=["src/"],
            exclude_patterns=["*test_*.py"],
        )

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        combined = backend._filter_and_score_results(results, request)
        legacy = self._legacy_filter_then_score(results, request)

        assert combined == legacy

    def test_exclude_patterns_glob_matching(self):
        """Test excluding files by glob patterns."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "src/test_main.py", "score": 0.8},
            {
                "chunk_id": "3",
                "repo": "test",
                "path": "tests/test_utils.py",
                "score": 0.7,
            },
            {"chunk_id": "4", "repo": "test", "path": "src/utils.py", "score": 0.6},
            {"chunk_id": "5", "repo": "test", "path": "config.json", "score": 0.5},
        ]

        request = SearchRequest(query="test", exclude_patterns=["**/test_*.py", "*.json"])

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should exclude test files and config files
        assert len(filtered) == 2
        assert any(r["path"] == "src/main.py" for r in filtered)
        assert any(r["path"] == "src/utils.py" for r in filtered)

    def test_exclude_patterns_multiple_patterns(self):
        """Test excluding files with multiple glob patterns."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.ts", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "src/test.spec.ts", "score": 0.8},
            {"chunk_id": "3", "repo": "test", "path": "config.toml", "score": 0.7},
            {"chunk_id": "4", "repo": "test", "path": "package.json", "score": 0.6},
            {"chunk_id": "5", "repo": "test", "path": "src/utils.ts", "score": 0.5},
        ]

        request = SearchRequest(query="test", exclude_patterns=["*.spec.ts", "*.toml", "*.json"])

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should only include production TypeScript files
        assert len(filtered) == 2
        assert all(
            isinstance(r["path"], str) and r["path"].endswith(".ts") and not r["path"].endswith(".spec.ts")
            for r in filtered
        )

    def test_exclude_paths_and_patterns_combined(self):
        """Test using both exclude_paths and exclude_patterns together."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "src/test_main.py", "score": 0.8},
            {
                "chunk_id": "3",
                "repo": "test",
                "path": "tests/test_utils.py",
                "score": 0.7,
            },
            {
                "chunk_id": "4",
                "repo": "test",
                "path": "node_modules/lib.js",
                "score": 0.6,
            },
            {"chunk_id": "5", "repo": "test", "path": "src/config.json", "score": 0.5},
            {"chunk_id": "6", "repo": "test", "path": "src/utils.py", "score": 0.4},
        ]

        request = SearchRequest(
            query="test",
            exclude_paths=["tests/", "node_modules/"],
            exclude_patterns=["test_*.py", "*.json"],
        )

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should exclude tests/, node_modules/, test_*.py, and *.json
        assert len(filtered) == 2
        assert any(r["path"] == "src/main.py" for r in filtered)
        assert any(r["path"] == "src/utils.py" for r in filtered)

    def test_positive_and_negative_filtering_combined(self):
        """Test combining path_prefix (positive) with negative filters."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "src/test_main.py", "score": 0.8},
            {"chunk_id": "3", "repo": "test", "path": "src/config.json", "score": 0.7},
            {
                "chunk_id": "4",
                "repo": "test",
                "path": "tests/test_utils.py",
                "score": 0.6,
            },
            {"chunk_id": "5", "repo": "test", "path": "docs/guide.md", "score": 0.5},
        ]

        request = SearchRequest(
            query="test",
            path_prefix=["src/"],  # Only include src/
            exclude_patterns=["test_*.py", "*.json"],  # But exclude tests and configs
        )

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should only include src/main.py
        assert len(filtered) == 1
        assert filtered[0]["path"] == "src/main.py"

    def test_normalize_paths_with_leading_slashes(self):
        """Test that path normalization handles leading ./ and /."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "./src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "/tests/test.py", "score": 0.8},
            {"chunk_id": "3", "repo": "test", "path": "src/utils.py", "score": 0.7},
        ]

        request = SearchRequest(query="test", exclude_paths=["tests/"])

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should properly normalize and exclude /tests/test.py
        assert len(filtered) == 2
        assert not any(isinstance(r["path"], str) and "test.py" in r["path"] for r in filtered)

    def test_empty_negative_filters(self):
        """Test that empty negative filters don't affect results."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "tests/test.py", "score": 0.8},
        ]

        request = SearchRequest(query="test", exclude_paths=[], exclude_patterns=[])

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should return all results
        assert len(filtered) == 2

    def test_no_negative_filters_specified(self):
        """Test that None negative filters don't affect results."""
        results = [
            {"chunk_id": "1", "repo": "test", "path": "src/main.py", "score": 0.9},
            {"chunk_id": "2", "repo": "test", "path": "tests/test.py", "score": 0.8},
        ]

        request = SearchRequest(
            query="test"
            # exclude_paths and exclude_patterns not specified
        )

        backend = KnowledgeSearchBackend(
            embedding_provider=cast(EmbeddingProvider, None),
            lance_store=cast(LanceDBStore, None),
            sql_store=cast(SQLiteMetadataStore, None),
        )

        filtered = backend._filter_and_score_results(results, request)

        # Should return all results
        assert len(filtered) == 2
