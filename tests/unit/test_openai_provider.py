"""Tests for OpenAI embedding provider."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from pb_kb.embeddings.provider import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_provider,
    set_default_provider,
    embed_texts,
)


class TestEmbeddingProvider:
    """Tests for base EmbeddingProvider (stub)."""

    def test_stub_provider_returns_zero_vectors(self):
        """Test that stub provider returns zero vectors with correct dimensions."""
        provider = EmbeddingProvider()

        # Test small model
        result = provider.embed_texts("small", ["test text 1", "test text 2"])
        assert len(result) == 2
        assert len(result[0]) == 1536
        assert all(val == 0.0 for val in result[0])

        # Test large model
        result = provider.embed_texts("large", ["test"])
        assert len(result) == 1
        assert len(result[0]) == 3072
        assert all(val == 0.0 for val in result[0])

    def test_stub_provider_raises_on_invalid_model(self):
        """Test that invalid model names raise ValueError."""
        provider = EmbeddingProvider()

        with pytest.raises(ValueError, match="Unsupported model"):
            provider.embed_texts("invalid", ["test"])


class TestOpenAIEmbeddingProvider:
    """Tests for OpenAIEmbeddingProvider."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        with patch('openai.OpenAI') as mock_openai_class:
            provider = OpenAIEmbeddingProvider(api_key="test-key-123")

            assert provider.api_key == "test-key-123"
            assert provider.batch_size == 100
            mock_openai_class.assert_called_once_with(api_key="test-key-123")

    def test_init_with_env_var(self):
        """Test initialization reading API key from environment."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key-456"}):
            with patch('openai.OpenAI') as mock_openai_class:
                provider = OpenAIEmbeddingProvider()

                assert provider.api_key == "env-key-456"
                mock_openai_class.assert_called_once_with(api_key="env-key-456")

    def test_init_without_api_key_raises(self):
        """Test that missing API key raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OpenAI API key is required"):
                OpenAIEmbeddingProvider()

    def test_embed_texts_single_batch(self):
        """Test embedding texts in a single batch."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.data = [
            Mock(embedding=[0.1] * 1536),
            Mock(embedding=[0.2] * 1536),
        ]

        with patch('openai.OpenAI') as mock_openai_class:
            mock_client = Mock()
            mock_client.embeddings.create.return_value = mock_response
            mock_openai_class.return_value = mock_client

            provider = OpenAIEmbeddingProvider(api_key="test-key")
            result = provider.embed_texts("small", ["text1", "text2"])

            assert len(result) == 2
            assert len(result[0]) == 1536
            assert result[0] == [0.1] * 1536
            assert result[1] == [0.2] * 1536

            # Verify API call
            mock_client.embeddings.create.assert_called_once_with(
                input=["text1", "text2"],
                model="text-embedding-3-small"
            )

    def test_embed_texts_multiple_batches(self):
        """Test embedding texts across multiple batches."""
        # Create 250 texts to test batching (batch_size=100)
        texts = [f"text{i}" for i in range(250)]

        # Mock OpenAI responses for each batch
        def create_mock_response(batch_size):
            mock_response = Mock()
            mock_response.data = [
                Mock(embedding=[float(i)] * 1536)
                for i in range(batch_size)
            ]
            return mock_response

        with patch('openai.OpenAI') as mock_openai_class:
            mock_client = Mock()
            mock_client.embeddings.create.side_effect = [
                create_mock_response(100),  # First batch
                create_mock_response(100),  # Second batch
                create_mock_response(50),   # Third batch
            ]
            mock_openai_class.return_value = mock_client

            provider = OpenAIEmbeddingProvider(api_key="test-key", batch_size=100)
            result = provider.embed_texts("small", texts)

            assert len(result) == 250
            assert mock_client.embeddings.create.call_count == 3

    def test_embed_texts_large_model(self):
        """Test embedding with large model."""
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.5] * 3072)]

        with patch('openai.OpenAI') as mock_openai_class:
            mock_client = Mock()
            mock_client.embeddings.create.return_value = mock_response
            mock_openai_class.return_value = mock_client

            provider = OpenAIEmbeddingProvider(api_key="test-key")
            result = provider.embed_texts("large", ["test"])

            assert len(result[0]) == 3072
            mock_client.embeddings.create.assert_called_once_with(
                input=["test"],
                model="text-embedding-3-large"
            )

    def test_embed_texts_empty_list(self):
        """Test embedding empty list returns empty list."""
        with patch('openai.OpenAI') as mock_openai_class:
            mock_client = Mock()
            mock_openai_class.return_value = mock_client

            provider = OpenAIEmbeddingProvider(api_key="test-key")
            result = provider.embed_texts("small", [])

            assert result == []
            mock_client.embeddings.create.assert_not_called()

    def test_embed_texts_retry_on_failure(self):
        """Test that retry logic works on API failures."""
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1] * 1536)]

        with patch('openai.OpenAI') as mock_openai_class:
            mock_client = Mock()
            # Fail twice, then succeed
            mock_client.embeddings.create.side_effect = [
                Exception("API Error 1"),
                Exception("API Error 2"),
                mock_response,
            ]
            mock_openai_class.return_value = mock_client

            provider = OpenAIEmbeddingProvider(api_key="test-key")
            result = provider.embed_texts("small", ["test"])

            assert len(result) == 1
            assert mock_client.embeddings.create.call_count == 3


class TestProviderFactory:
    """Tests for provider factory and global management."""

    def test_create_stub_provider(self):
        """Test creating stub provider."""
        provider = create_provider("stub")
        assert isinstance(provider, EmbeddingProvider)
        assert not isinstance(provider, OpenAIEmbeddingProvider)

    def test_create_openai_provider(self):
        """Test creating OpenAI provider."""
        with patch('openai.OpenAI'):
            provider = create_provider("openai", api_key="test-key")
            assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_create_invalid_provider(self):
        """Test that invalid provider type raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported provider type"):
            create_provider("invalid")

    def test_set_default_provider(self):
        """Test setting global default provider."""
        # Create a custom provider
        with patch('openai.OpenAI'):
            custom_provider = OpenAIEmbeddingProvider(api_key="test-key")
            set_default_provider(custom_provider)

            # Test that convenience function uses new default
            mock_response = Mock()
            mock_response.data = [Mock(embedding=[0.9] * 1536)]
            custom_provider.client.embeddings.create.return_value = mock_response

            result = embed_texts("small", ["test"])
            assert result[0] == [0.9] * 1536


class TestIntegration:
    """Integration tests (can be skipped if no API key available)."""

    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set"
    )
    def test_real_openai_api(self):
        """Test real OpenAI API call (requires valid API key)."""
        provider = OpenAIEmbeddingProvider()
        result = provider.embed_texts("small", ["Hello, world!"])

        assert len(result) == 1
        assert len(result[0]) == 1536
        # Check that it's not all zeros (real embedding)
        assert not all(val == 0.0 for val in result[0])
        # Check that embeddings are normalized (roughly)
        import math
        magnitude = math.sqrt(sum(val ** 2 for val in result[0]))
        assert 0.9 < magnitude < 1.1  # OpenAI embeddings are normalized
