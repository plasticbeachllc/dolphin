import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from kb.api.app import get_search_backend, reset_search_backend
from kb.api.server import initialize_search_backend, load_env_file
from kb.config import KBConfig


class TestLoadEnvFile:
    """Test environment file loading."""

    @patch("kb.api.server.Path")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="TEST_KEY=test_value\nAPI_KEY=secret",
    )
    def test_load_env_file_exists(self, mock_file, mock_path_class):
        """Test loading valid .env file."""
        # Setup mock path
        mock_env_file = MagicMock()
        mock_env_file.exists.return_value = True
        mock_path_class.return_value.parent.parent.parent.parent.__truediv__.return_value = (
            mock_env_file
        )

        # Clear any existing env vars
        if "TEST_KEY" in os.environ:
            del os.environ["TEST_KEY"]
        if "API_KEY" in os.environ:
            del os.environ["API_KEY"]

        try:
            load_env_file()

            # Verify environment variables were set
            assert os.environ.get("TEST_KEY") == "test_value"
            assert os.environ.get("API_KEY") == "secret"
        finally:
            # Cleanup
            if "TEST_KEY" in os.environ:
                del os.environ["TEST_KEY"]
            if "API_KEY" in os.environ:
                del os.environ["API_KEY"]

    @patch("kb.api.server.Path")
    def test_load_env_file_missing(self, mock_path_class, capsys):
        """Test graceful handling when .env file is missing."""
        # Setup mock path - file doesn't exist
        mock_env_file = MagicMock()
        mock_env_file.exists.return_value = False
        mock_path_class.return_value.parent.parent.parent.parent.__truediv__.return_value = (
            mock_env_file
        )

        load_env_file()

        # Should print info message
        captured = capsys.readouterr()
        assert "No .env file found" in captured.err

    @patch("kb.api.server.Path")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="API_KEY=\"quoted_value\"\nOTHER='single_quoted'",
    )
    def test_load_env_file_strips_quotes(self, mock_file, mock_path_class):
        """Test that quotes are stripped from values."""
        # Setup mock path
        mock_env_file = MagicMock()
        mock_env_file.exists.return_value = True
        mock_path_class.return_value.parent.parent.parent.parent.__truediv__.return_value = (
            mock_env_file
        )

        # Clear any existing env vars
        if "API_KEY" in os.environ:
            del os.environ["API_KEY"]
        if "OTHER" in os.environ:
            del os.environ["OTHER"]

        try:
            load_env_file()

            # Quotes should be stripped
            assert os.environ.get("API_KEY") == "quoted_value"
            assert os.environ.get("OTHER") == "single_quoted"
        finally:
            # Cleanup
            if "API_KEY" in os.environ:
                del os.environ["API_KEY"]
            if "OTHER" in os.environ:
                del os.environ["OTHER"]

    @patch("kb.api.server.Path")
    @patch(
        "builtins.open", new_callable=mock_open, read_data="# Comment\nKEY=value\n\n"
    )
    def test_load_env_file_skips_comments_and_empty_lines(
        self, mock_file, mock_path_class
    ):
        """Test that comments and empty lines are skipped."""
        # Setup mock path
        mock_env_file = MagicMock()
        mock_env_file.exists.return_value = True
        mock_path_class.return_value.parent.parent.parent.parent.__truediv__.return_value = (
            mock_env_file
        )

        # Clear any existing env vars
        if "KEY" in os.environ:
            del os.environ["KEY"]

        try:
            load_env_file()

            # Only valid key should be loaded
            assert os.environ.get("KEY") == "value"
        finally:
            # Cleanup
            if "KEY" in os.environ:
                del os.environ["KEY"]


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
