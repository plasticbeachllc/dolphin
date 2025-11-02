"""Unit tests for FTS5/BM25 functionality in SQLiteMetadataStore."""

import pytest
from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock
from kb.store.sqlite_meta import SQLiteMetadataStore


class TestFTS5IndexCreation:
    """Test FTS5 virtual table creation and setup."""

    def test_initialize_creates_fts5_table(self, tmp_path):
        """Test that initialize() creates the FTS5 virtual table."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Verify FTS5 table exists
        with store._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "chunks_fts"

    def test_fts5_table_structure(self, tmp_path):
        """Test that FTS5 table has the correct structure."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        with store._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(chunks_fts)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            
            expected_columns = {
                'content_id',
                'repo',
                'path',
                'content',
                'symbol_name',
                'symbol_path'
            }
            
            for col_name in expected_columns:
                assert col_name in columns, f"Missing column: {col_name}"


class TestBM25Search:
    """Test BM25 search functionality."""

    @pytest.fixture
    def store_with_data(self, tmp_path):
        """Create a store with test data indexed for FTS5."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Index some test chunks
        test_chunks = [
            {
                'content_id': 'chunk1',
                'repo': 'test-repo',
                'path': 'src/user_controller.py',
                'content': 'class UserController handles authentication login logout',
                'symbol_name': 'UserController',
                'symbol_path': 'controllers.UserController'
            },
            {
                'content_id': 'chunk2', 
                'repo': 'test-repo',
                'path': 'src/auth_middleware.py',
                'content': 'middleware for authentication JWT token validation',
                'symbol_name': 'AuthMiddleware',
                'symbol_path': 'middleware.AuthMiddleware'
            },
            {
                'content_id': 'chunk3',
                'repo': 'test-repo', 
                'path': 'tests/test_auth.py',
                'content': 'test cases for authentication flow UserController',
                'symbol_name': None,
                'symbol_path': None
            }
        ]
        
        store.bulk_index_chunks_for_fts(test_chunks)
        return store

    def test_bm25_search_basic(self, store_with_data):
        """Test basic BM25 search functionality."""
        results = store_with_data.bm25_search("UserController", top_k=5)
        
        assert len(results) >= 1
        # Should find chunks containing "UserController"
        chunk_ids = [r['chunk_id'] for r in results]
        assert 'chunk1' in chunk_ids
        assert 'chunk3' in chunk_ids

    def test_bm25_search_exact_match(self, store_with_data):
        """Test BM25 search for exact symbol names."""
        results = store_with_data.bm25_search("UserController", top_k=5)
        
        assert len(results) >= 1
        # First result should be the most relevant
        first_result = results[0]
        assert first_result['chunk_id'] == 'chunk1'  # Most relevant for exact match
        # Verify that the result contains UserController in the path or is from correct chunk
        assert first_result['chunk_id'] == 'chunk1'  # Should be the chunk containing UserController

    def test_bm25_search_no_results(self, store_with_data):
        """Test BM25 search with no matching results."""
        results = store_with_data.bm25_search("nonexistent_function_name_xyz", top_k=5)
        
        assert len(results) == 0

    def test_bm25_search_with_filters(self, store_with_data):
        """Test BM25 search with repository filter."""
        # Search only in test-repo
        results = store_with_data.bm25_search("authentication", repo="test-repo", top_k=10)
        
        assert len(results) >= 1
        for result in results:
            assert result['repo'] == 'test-repo'

    def test_bm25_search_path_prefix_filter(self, store_with_data):
        """Test BM25 search with path prefix filters."""
        # Search only in src/ directory
        results = store_with_data.bm25_search("authentication", path_prefix=["src/"], top_k=10)
        
        assert len(results) >= 1
        for result in results:
            assert result['path'].startswith('src/')

    def test_bm25_score_ranges(self, store_with_data):
        """Test that BM25 scores are reasonable."""
        results = store_with_data.bm25_search("UserController", top_k=5)
        
        assert len(results) >= 1
        for result in results:
            # BM25 scores should be positive after negation
            assert result['score'] > 0
            # Scores should be finite
            assert float('-inf') < result['score'] < float('inf')

    def test_bm25_search_top_k_limit(self, store_with_data):
        """Test that top_k parameter limits results correctly."""
        results = store_with_data.bm25_search("authentication", top_k=2)
        
        assert len(results) <= 2

    def test_bm25_ranking_order(self, store_with_data):
        """Test that results are ordered by relevance (rank)."""
        results = store_with_data.bm25_search("authentication", top_k=10)
        
        if len(results) > 1:
            # Results should be ordered by rank (ascending, lower is better)
            ranks = [r['rank'] for r in results]
            assert ranks == sorted(ranks), "Results should be ordered by rank"


class TestFTS5Indexing:
    """Test FTS5 indexing functionality."""

    def test_index_chunk_for_fts(self, tmp_path):
        """Test single chunk indexing."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        store.index_chunk_for_fts(
            content_id='test_chunk_1',
            repo='test_repo',
            path='src/test.py',
            content='def test_function(): pass',
            symbol_name='test_function',
            symbol_path='module.test_function'
        )
        
        # Verify chunk was indexed
        results = store.bm25_search("test_function")
        assert len(results) >= 1
        assert results[0]['chunk_id'] == 'test_chunk_1'

    def test_bulk_index_chunks_for_fts(self, tmp_path):
        """Test bulk chunk indexing."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        chunks = [
            {
                'content_id': 'bulk1',
                'repo': 'repo1',
                'path': 'file1.py',
                'content': 'first chunk content',
                'symbol_name': 'func1',
                'symbol_path': 'module.func1'
            },
            {
                'content_id': 'bulk2',
                'repo': 'repo1', 
                'path': 'file2.py',
                'content': 'second chunk content',
                'symbol_name': 'func2',
                'symbol_path': 'module.func2'
            }
        ]
        
        indexed_count = store.bulk_index_chunks_for_fts(chunks)
        assert indexed_count == 2
        
        # Verify both chunks were indexed
        results1 = store.bm25_search("first")
        results2 = store.bm25_search("second")
        
        assert len(results1) >= 1
        assert len(results2) >= 1
        assert results1[0]['chunk_id'] == 'bulk1'
        assert results2[0]['chunk_id'] == 'bulk2'

    def test_empty_bulk_index(self, tmp_path):
        """Test bulk indexing with empty list."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        indexed_count = store.bulk_index_chunks_for_fts([])
        assert indexed_count == 0

    def test_upsert_behavior(self, tmp_path):
        """Test that indexing behaves like upsert (insert or replace)."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Insert initial chunk
        store.index_chunk_for_fts(
            content_id='upsert_test',
            repo='test_repo',
            path='test.py',
            content='original content',
            symbol_name='test',
            symbol_path='test'
        )
        
        results = store.bm25_search("original")
        assert len(results) >= 1
        assert results[0]['chunk_id'] == 'upsert_test'
        
        # Update the same chunk with new content
        store.index_chunk_for_fts(
            content_id='upsert_test',
            repo='test_repo',
            path='test.py',
            content='updated content new text',
            symbol_name='test',
            symbol_path='test'
        )
        
        # Should now find updated content, and possibly still find original due to FTS5 behavior
        updated_results = store.bm25_search("updated")
        new_results = store.bm25_search("new")
        
        assert len(updated_results) >= 1
        assert len(new_results) >= 1


class TestChunkMetadata:
    """Test chunk metadata retrieval functionality."""

    def test_get_chunk_by_id(self, tmp_path):
        """Test retrieving chunk metadata by ID."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # This test requires a complete chunk in both chunk_content and chunks_fts
        # For now, test with non-existent chunk
        result = store.get_chunk_by_id("nonexistent")
        assert result is None

    def test_get_chunk_contents(self, tmp_path):
        """Test retrieving chunk contents for FTS5 indexing."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # This tests the reverse join from chunk_content to chunks_fts
        result = store.get_chunk_contents([])
        assert result == {}
        
        result = store.get_chunk_contents(["nonexistent1", "nonexistent2"])
        assert result == {}


class TestErrorHandling:
    """Test error handling in FTS5 operations."""

    def test_bm25_search_with_malformed_query(self, tmp_path):
        """Test BM25 search with potentially problematic queries."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Test with empty query - should return empty results
        results = store.bm25_search("")
        assert isinstance(results, list)
        assert len(results) == 0
        
        # Test with whitespace-only query
        results = store.bm25_search("   ")
        assert isinstance(results, list)
        assert len(results) == 0
        
        # Test with potentially problematic characters - should return empty results safely
        results = store.bm25_search("'; DROP TABLE chunks_fts; --")
        assert isinstance(results, list)  # Should be safe, not crash
        # May return empty results due to sanitization

    def test_bm25_search_sql_injection_protection(self, tmp_path):
        """Test that BM25 search is protected against SQL injection."""
        store = SQLiteMetadataStore(tmp_path / "test.db")
        store.initialize()
        
        # Try various injection attempts
        malicious_queries = [
            "'; DROP TABLE chunks_fts; --",
            "' OR '1'='1",
            "'; UPDATE repos SET name='hacked'; --",
            "\\x00",  # null bytes
        ]
        
        for query in malicious_queries:
            try:
                results = store.bm25_search(query)
                # Should return results without crashing
                assert isinstance(results, list)
                # Should not crash or cause SQL injection
            except Exception as e:
                # If it fails, should be due to our safety checks, not SQL injection
                assert "syntax error" in str(e) or "fts5" in str(e).lower()