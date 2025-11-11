import pytest
from pathlib import Path
from unittest.mock import patch
from kb.api.search_backend import create_search_backend
from kb.api.app import SearchRequest

class TestCacheSearchBackendIntegration:

    @pytest.mark.integration
    def test_search_backend_caches_results(self, tmp_path):
        """Verify that the search backend caches results."""
        backend = create_search_backend(
            store_root=tmp_path,
            embedding_provider_type="stub",
            cache_enabled=True,
        )
        request = SearchRequest(query="test query", embed_model="small")
        
        # Patch the embedding provider to monitor calls, since it's called after the cache check
        with patch.object(backend.embedding_provider, 'embed_texts', return_value=[[0.1]*1536]) as mock_embed:
            # First call, should miss cache and call the provider
            backend.search(request)
            mock_embed.assert_called_once()
            
            # Second call, should hit cache
            backend.search(request)
            # The mock should still only have been called once
            mock_embed.assert_called_once()