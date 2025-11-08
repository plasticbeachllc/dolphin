"""Embedding provider interface with retry logic.

This module provides implementations for embedding text with retry logic.
Supports both stub (zero-vector) and OpenAI API providers.
"""

from __future__ import annotations

import os
from typing import List, Optional

from ..ingest.error_logging import with_retry
from ..cache import QueryCache

SUPPORTED_MODELS = {
    'small': 1536,
    'large': 3072,
}

# Map internal model names to OpenAI model names
OPENAI_MODEL_MAP = {
    'small': 'text-embedding-3-small',  # 1536 dimensions
    'large': 'text-embedding-3-large',  # 3072 dimensions
}


class EmbeddingProvider:
    """Base class for embedding providers with retry logic."""

    def __init__(self):
        self.model_dimensions = SUPPORTED_MODELS.copy()

    @with_retry(max_attempts=3, delays=(1.0, 2.0, 4.0))
    def embed_texts(self, model: str, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts using the specified model.

        Args:
            model: The embedding model to use ('small' or 'large')
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)

        Raises:
            ValueError: If model is not supported
        """
        if model not in self.model_dimensions:
            raise ValueError(f"Unsupported model: {model}. Must be 'small' or 'large'")

        dimension = self.model_dimensions[model]

        # Stub implementation: Return zero vectors with expected dimensions
        # Override this method in subclasses for real implementations
        return [[0.0] * dimension for _ in texts]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI API-based embedding provider with retry logic."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        batch_size: int = 100,
        cache: Optional[QueryCache] = None,
    ):
        """Initialize OpenAI embedding provider.

        Args:
            api_key: OpenAI API key. If None, reads from OPENAI_API_KEY env var.
            batch_size: Maximum number of texts to embed in a single API call.
            cache: Optional QueryCache instance for caching embeddings.

        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        super().__init__()
        
        # Cache instance
        self.cache = cache

        # Lazy import to avoid requiring openai if using stub provider
        try:
            from openai import OpenAI
            self._openai_module = OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI package is required for OpenAIEmbeddingProvider. "
                "Install with: pip install openai"
            )

        # Get API key from parameter or environment
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Provide via api_key parameter "
                "or set OPENAI_API_KEY environment variable."
            )

        self.batch_size = batch_size
        self.client = self._openai_module(api_key=self.api_key)
        
        # Validate API key immediately with a minimal test request
        self._validate_api_key()

    def _validate_api_key(self) -> None:
        """Validate API key by making a minimal test request.
        
        Raises:
            RuntimeError: If API key is invalid or authentication fails
        """
        try:
            # Make a minimal test request with a tiny payload
            self.client.embeddings.create(
                input=["test"],
                model="text-embedding-3-small"
            )
            # If we get here, the API key is valid
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid" in error_msg.lower() or "incorrect" in error_msg.lower():
                raise RuntimeError(
                    f"\n{'='*70}\n"
                    f"OPENAI API KEY VALIDATION FAILED\n"
                    f"{'='*70}\n"
                    f"The OpenAI API key is invalid or has expired.\n\n"
                    f"To fix this:\n"
                    f"  1. Get a valid API key from: https://platform.openai.com/account/api-keys\n"
                    f"  2. Set it in your environment:\n"
                    f"     export OPENAI_API_KEY=\"sk-your-actual-key-here\"\n"
                    f"  3. Or add to your shell profile (~/.zshrc or ~/.bashrc)\n\n"
                    f"Original error: {error_msg}\n"
                    f"{'='*70}\n"
                )
            # For other errors, raise the original exception
            raise

    @with_retry(max_attempts=3, delays=(1.0, 2.0, 4.0))
    def embed_texts(self, model: str, texts: List[str]) -> List[List[float]]:
        """Embed texts using OpenAI API.

        Args:
            model: The embedding model to use ('small' or 'large')
            texts: List of text strings to embed

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If model is not supported
        """
        if model not in self.model_dimensions:
            raise ValueError(f"Unsupported model: {model}. Must be 'small' or 'large'")

        if not texts:
            return []

        # Get OpenAI model name
        openai_model = OPENAI_MODEL_MAP[model]

        # Check cache for each text and collect uncached texts
        all_embeddings: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []
        
        for i, text in enumerate(texts):
            if self.cache:
                cached = self.cache.get_embedding(text, model)
                if cached is not None:
                    all_embeddings[i] = cached
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
        
        # Process uncached texts in batches
        if uncached_texts:
            for batch_start in range(0, len(uncached_texts), self.batch_size):
                batch = uncached_texts[batch_start:batch_start + self.batch_size]
                batch_indices = uncached_indices[batch_start:batch_start + self.batch_size]

                # Call OpenAI API
                response = self.client.embeddings.create(
                    input=batch,
                    model=openai_model
                )

                # Extract embeddings and cache them
                for j, item in enumerate(response.data):
                    embedding = item.embedding
                    original_idx = batch_indices[j]
                    all_embeddings[original_idx] = embedding
                    
                    # Cache the embedding
                    if self.cache:
                        self.cache.set_embedding(
                            uncached_texts[batch_start + j],
                            model,
                            embedding
                        )

        return all_embeddings  # type: ignore


# Global instance for convenience - starts with stub provider
_default_provider: EmbeddingProvider = EmbeddingProvider()


def embed_texts(model: str, texts: List[str]) -> List[List[float]]:
    """Convenience function to embed texts using the default provider.
    
    Args:
        model: The embedding model to use ('small' or 'large')
        texts: List of text strings to embed
        
    Returns:
        List of embedding vectors
    """
    return _default_provider.embed_texts(model, texts)


def embed_texts_with_retry(model: str, texts: List[str]) -> List[List[float]]:
    """Convenience function with explicit retry for use in pipeline.

    This is an alias for embed_texts that includes retry logic.
    """
    return embed_texts(model, texts)


def create_provider(provider_type: str = "stub", **kwargs) -> EmbeddingProvider:
    """Factory function to create an embedding provider.

    Args:
        provider_type: Type of provider ('stub' or 'openai')
        **kwargs: Additional arguments passed to provider constructor

    Returns:
        An embedding provider instance

    Raises:
        ValueError: If provider_type is not supported
    """
    if provider_type == "stub":
        return EmbeddingProvider()
    elif provider_type == "openai":
        return OpenAIEmbeddingProvider(**kwargs)
    else:
        raise ValueError(
            f"Unsupported provider type: {provider_type}. "
            "Must be 'stub' or 'openai'."
        )


def set_default_provider(provider: EmbeddingProvider) -> None:
    """Set the global default provider.

    Args:
        provider: The provider instance to use as default
    """
    global _default_provider
    _default_provider = provider