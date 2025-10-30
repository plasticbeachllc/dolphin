"""Tests for API server initialization."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pb_kb.api.server import initialize_search_backend
from pb_kb.api.app import get_search_backend, reset_search_backend


class TestServerInitialization:
    """Tests for server initialization with search backend."""

    def teardown_method(self):
        """Reset search backend after each test."""
        reset_search_backend()

    def test_initialize_with_stub_provider(self):
        """Test initialization with stub provider (no API key needed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dict = {
                "store_root": tmpdir,
                "embedding": {
                    "provider": "stub",
                }
            }

            with patch("pb_kb.api.server.load_config") as mock_load_config:
                # Mock config
                from pb_kb.config import KBConfig
                mock_config = KBConfig.from_mapping(config_dict)
                mock_load_config.return_value = mock_config

                # Initialize
                initialize_search_backend()

                # Verify backend is set
                backend = get_search_backend()
                assert backend is not None
                assert backend.__class__.__name__ == "KnowledgeSearchBackend"

    def test_initialize_with_openai_provider(self):
        """Test initialization with OpenAI provider (with API key)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dict = {
                "store_root": tmpdir,
                "embedding": {
                    "provider": "openai",
                    "api_key_env": "TEST_OPENAI_API_KEY",
                    "batch_size": 50,
                }
            }

            # Mock environment with API key
            with patch.dict("os.environ", {"TEST_OPENAI_API_KEY": "test-key"}):
                with patch("pb_kb.api.server.load_config") as mock_load_config:
                    with patch("openai.OpenAI"):  # Mock OpenAI client
                        # Mock config
                        from pb_kb.config import KBConfig
                        mock_config = KBConfig.from_mapping(config_dict)
                        mock_load_config.return_value = mock_config

                        # Initialize
                        initialize_search_backend()

                        # Verify backend is set with OpenAI provider
                        backend = get_search_backend()
                        assert backend is not None
                        assert backend.embedding_provider.__class__.__name__ == "OpenAIEmbeddingProvider"

    def test_initialize_fallback_to_stub_without_api_key(self):
        """Test that initialization falls back to stub if OpenAI key missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dict = {
                "store_root": tmpdir,
                "embedding": {
                    "provider": "openai",
                    "api_key_env": "MISSING_API_KEY",
                }
            }

            # No API key in environment
            with patch.dict("os.environ", {}, clear=True):
                with patch("pb_kb.api.server.load_config") as mock_load_config:
                    # Mock config
                    from pb_kb.config import KBConfig
                    mock_config = KBConfig.from_mapping(config_dict)
                    mock_load_config.return_value = mock_config

                    # Initialize (should fall back to stub)
                    initialize_search_backend()

                    # Verify backend is set with stub provider
                    backend = get_search_backend()
                    assert backend is not None
                    # Should use base EmbeddingProvider (stub)
                    assert backend.embedding_provider.__class__.__name__ == "EmbeddingProvider"
