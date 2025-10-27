"""Embedding provider interface with retry logic.

This module provides a stub implementation for embedding text with retry logic.
In Phase 6, this returns zero vectors with expected dimensions.
"""

from __future__ import annotations

from typing import List

from ..ingest.error_logging import with_retry

SUPPORTED_MODELS = {
    'small': 1536,
    'large': 3072,
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
        
        # Phase 6: Return zero vectors with expected dimensions
        # Replace this with actual embedding API calls in later phases
        return [[0.0] * dimension for _ in texts]


# Global instance for convenience
_default_provider = EmbeddingProvider()


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