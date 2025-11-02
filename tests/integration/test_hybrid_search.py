import pytest
from pathlib import Path
import tempfile
from unittest.mock import patch
from kb.api.search_backend import create_search_backend
from kb.api.app import SearchRequest

@pytest.fixture
def hybrid_backend():
    with tempfile.TemporaryDirectory() as temp_dir:
        store_root = Path(temp_dir)
        # Use the stable factory with kwargs
        backend = create_search_backend(store_root=store_root, hybrid_search_enabled=True)
        yield backend

class TestHybridSearch:
    def test_hybrid_search_backend_creation(self, hybrid_backend):
        assert hybrid_backend.hybrid_search_enabled

    def test_result_formatting(self, hybrid_backend):
        """Ensure search returns a list, even if empty."""
        request = SearchRequest(query="test")
        with patch.object(hybrid_backend.lance_store, 'query', return_value=[]), \
             patch.object(hybrid_backend.sql_store, 'bm25_search', return_value=[]):
            results = hybrid_backend.search(request)
            assert isinstance(results, list)

class TestErrorHandling:
    def test_fts5_failure_fallback(self, hybrid_backend):
        """Test fallback to vector-only search when FTS5 fails."""
        request = SearchRequest(query="test")
        # Simulate an FTS error
        with patch.object(hybrid_backend.sql_store, 'bm25_search', side_effect=Exception("FTS Error")), \
             patch.object(hybrid_backend.lance_store, 'query', return_value=[{'id': 'vec1', '_distance': 0.5}]):
            
            results = hybrid_backend.search(request)
            # Should still return the vector result
            assert len(results) == 1
            assert results[0]['chunk_id'] == 'vec1'