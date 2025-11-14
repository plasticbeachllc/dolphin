import tempfile
from pathlib import Path
from unittest.mock import patch

from kb.api.server import initialize_search_backend
from kb.api.app import get_search_backend, reset_search_backend
from kb.config import KBConfig


class TestServerInitialization:
    """Tests for server initialization logic."""

    def teardown_method(self):
        """Reset search backend after each test."""
        reset_search_backend()

    def test_initialize_with_stub_provider(self):
        """Test initialization with stub provider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KBConfig(store_root=Path(tmpdir), embedding_provider="stub")
            with patch("kb.api.server.load_config", return_value=config):
                initialize_search_backend()
                backend = get_search_backend()
                assert backend is not None
                assert (
                    backend.embedding_provider.__class__.__name__ == "EmbeddingProvider"
                )

    def test_initialize_with_openai_provider(self):
        """Test initialization with OpenAI provider and API key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KBConfig(
                store_root=Path(tmpdir),
                embedding_provider="openai",
                openai_api_key_env="TEST_OPENAI_KEY",
            )
            with (
                patch.dict("os.environ", {"TEST_OPENAI_KEY": "test-key"}),
                patch("kb.api.server.load_config", return_value=config),
                patch("kb.api.search_backend.create_provider") as mock_create,
            ):
                # Mock the create_provider to return OpenAIEmbeddingProvider without validation
                from kb.embeddings.provider import OpenAIEmbeddingProvider

                mock_provider = OpenAIEmbeddingProvider(
                    api_key="test-key", validate_key=False
                )
                mock_create.return_value = mock_provider

                initialize_search_backend()
                backend = get_search_backend()
                assert backend is not None
                # The test mocks create_provider, so we check if it was called with openai
                mock_create.assert_called_once()

    def test_fallback_to_stub_without_api_key(self):
        """Test fallback to stub provider if OpenAI key is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KBConfig(
                store_root=Path(tmpdir),
                embedding_provider="openai",
                openai_api_key_env="MISSING_KEY",
            )
            with (
                patch.dict("os.environ", {}, clear=True),
                patch("kb.api.server.load_config", return_value=config),
            ):
                initialize_search_backend()
                backend = get_search_backend()
                assert backend is not None
                assert (
                    backend.embedding_provider.__class__.__name__ == "EmbeddingProvider"
                )
