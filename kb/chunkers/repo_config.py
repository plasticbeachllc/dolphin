"""Repository-specific chunking configuration system.

This module provides per-repository chunking configuration via TOML files,
allowing customization of token window sizes, per-language overrides, and
embedding model settings for semantic retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]

__all__ = ["RepoChunkingConfig", "load_repo_chunking_config"]

_log = logging.getLogger(__name__)

# Default configuration values aligned with semantic retrieval best practices
DEFAULT_WINDOW_SIZE = 350
DEFAULT_OVERLAP_PCT = 0.10
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_TOKENIZER_ENCODING = "cl100k_base"

# Per-language window size defaults (in tokens)
# Larger window sizes for config files reduce over-chunking and prevent
# them from dominating search results via BM25 inflation
DEFAULT_PER_LANGUAGE = {
    "python": 512,
    "javascript": 350,
    "typescript": 350,
    "typescriptreact": 350,
    "java": 512,
    "cpp": 512,
    "c": 512,
    "go": 400,
    "rust": 400,
    "markdown": 256,
    "text": 256,
    "json": 400,      # Increased from 128 to reduce config file chunk count
    "toml": 512,      # Increased from 128 to reduce config file chunk count
    "yaml": 400,      # Increased from 128 to reduce config file chunk count
}


@dataclass
class RepoChunkingConfig:
    """Configuration for chunking files in a specific repository.
    
    Attributes:
        repo_path: Absolute path to the repository root
        default_window_size: Default token window size for all files
        per_language: Language-specific token window size overrides
        embedding_model: OpenAI embedding model name
        tokenizer_encoding: Tokenizer encoding name (e.g., "cl100k_base")
        overlap_pct: Percentage of overlap between consecutive chunks (0.0-1.0)
    """
    
    repo_path: Path
    default_window_size: int = DEFAULT_WINDOW_SIZE
    per_language: dict[str, int] = field(default_factory=lambda: DEFAULT_PER_LANGUAGE.copy())
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    tokenizer_encoding: str = DEFAULT_TOKENIZER_ENCODING
    overlap_pct: float = DEFAULT_OVERLAP_PCT
    
    def get_window_size_for_language(self, language: str) -> int:
        """Get the configured window size for a specific language.
        
        Args:
            language: Language identifier (e.g., "python", "typescript")
            
        Returns:
            Token window size for the language, or default if not configured
        """
        return self.per_language.get(language, self.default_window_size)
    
    def get_overlap_tokens(self, window_size: int | None = None) -> int:
        """Calculate the overlap token count for a given window size.
        
        Args:
            window_size: Window size in tokens (uses default if None)
            
        Returns:
            Number of tokens for overlap between consecutive chunks
        """
        size = window_size or self.default_window_size
        return max(0, int(size * self.overlap_pct))


def load_repo_chunking_config(repo_path: Path) -> RepoChunkingConfig:
    """Load chunking configuration from a repository's .dolphin/chunking_config.toml file.
    
    If the configuration file doesn't exist, returns a config with sensible defaults.
    
    Args:
        repo_path: Path to the repository root
        
    Returns:
        RepoChunkingConfig instance with loaded or default configuration
        
    Raises:
        ValueError: If the TOML file is malformed or contains invalid values
    """
    repo_path = Path(repo_path).expanduser().resolve()
    config_file = repo_path / ".dolphin" / "chunking_config.toml"
    
    # If config file doesn't exist, return defaults
    if not config_file.exists():
        _log.debug(
            "No chunking config found at %s, using defaults (window_size=%d)",
            config_file,
            DEFAULT_WINDOW_SIZE,
        )
        return RepoChunkingConfig(
            repo_path=repo_path,
            default_window_size=DEFAULT_WINDOW_SIZE,
            per_language=DEFAULT_PER_LANGUAGE.copy(),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            tokenizer_encoding=DEFAULT_TOKENIZER_ENCODING,
            overlap_pct=DEFAULT_OVERLAP_PCT,
        )
    
    # Load and parse TOML configuration
    try:
        with config_file.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse TOML config at {config_file}: {e}") from e
    
    # Extract configuration values with validation
    default_window = data.get("default_window_size", DEFAULT_WINDOW_SIZE)
    if not isinstance(default_window, int) or default_window <= 0:
        raise ValueError(
            f"default_window_size must be a positive integer, got: {default_window}"
        )
    
    # Per-language overrides
    per_language = DEFAULT_PER_LANGUAGE.copy()
    if "per_language" in data:
        lang_overrides = data["per_language"]
        if not isinstance(lang_overrides, Mapping):
            raise ValueError("per_language must be a mapping/table")
        for lang, size in lang_overrides.items():
            if not isinstance(size, int) or size <= 0:
                _log.warning(
                    "Ignoring invalid window size for language %s: %s", lang, size
                )
                continue
            per_language[str(lang)] = size
    
    # Embedding configuration
    embeddings_section = data.get("embeddings", {})
    embedding_model = embeddings_section.get("model", DEFAULT_EMBEDDING_MODEL)
    if not isinstance(embedding_model, str):
        embedding_model = DEFAULT_EMBEDDING_MODEL
    
    # Tokenizer configuration
    tokenizer_section = data.get("tokenizer", {})
    tokenizer_encoding = tokenizer_section.get("encoding", DEFAULT_TOKENIZER_ENCODING)
    if not isinstance(tokenizer_encoding, str):
        tokenizer_encoding = DEFAULT_TOKENIZER_ENCODING
    
    # Overlap percentage (optional, not in TOML spec but useful)
    overlap_pct = data.get("overlap_pct", DEFAULT_OVERLAP_PCT)
    if not isinstance(overlap_pct, (int, float)) or not (0.0 <= overlap_pct <= 1.0):
        _log.warning(
            "Invalid overlap_pct %s, using default %f", overlap_pct, DEFAULT_OVERLAP_PCT
        )
        overlap_pct = DEFAULT_OVERLAP_PCT
    
    _log.info(
        "Loaded chunking config from %s (default_window_size=%d, model=%s)",
        config_file,
        default_window,
        embedding_model,
    )
    
    return RepoChunkingConfig(
        repo_path=repo_path,
        default_window_size=default_window,
        per_language=per_language,
        embedding_model=embedding_model,
        tokenizer_encoding=tokenizer_encoding,
        overlap_pct=overlap_pct,
    )
