"""Chunker registry and routing system.

This module provides unified access to all chunkers with automatic routing
based on file extensions and language identifiers. It integrates with the
configuration system to support per-language token window sizes and other
chunking parameters.

Architecture:
    - Extension → Language → Chunker Function
    - Configuration-driven mappings loaded from .dolphin/config.toml
    - Per-repository overrides supported via .dolphin/chunking_config.toml
    
Usage:
    chunker = get_chunker(language="python")
    chunks = chunker(text, model="small", token_target=400)
    
    # Or use the high-level interface:
    chunks = chunk_file(
        abs_path=Path("/path/to/file.py"),
        rel_path="src/file.py",
        language="python",
        text=source_code,
        repo_config=config,
    )
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .fallback_chunker import chunk_text
from .md_chunker import chunk_markdown
from .py_chunker import chunk_source as chunk_python
from .repo_config import RepoChunkingConfig
from .ts_chunker import chunk_source as chunk_typescript
from .types import Chunk

__all__ = [
    "get_chunker",
    "get_chunker_for_file",
    "chunk_file",
    "detect_language_from_extension",
    "ChunkerFunction",
]

_log = logging.getLogger(__name__)

# Type alias for chunker functions (avoid importing ChunkList directly)
ChunkerFunction = Callable[..., List]  # Returns list of Chunk objects

# Built-in chunkers mapped to language identifiers
_BUILTIN_CHUNKERS: Dict[str, ChunkerFunction] = {
    "python": chunk_python,
    "typescript": chunk_typescript,
    "typescriptreact": chunk_typescript,
    "javascript": lambda text, **kwargs: chunk_typescript(text, lang="javascript", **kwargs),
    "javascriptreact": lambda text, **kwargs: chunk_typescript(text, lang="javascript", **kwargs),
    "markdown": chunk_markdown,
}


@lru_cache(maxsize=1)
def _load_global_extension_map() -> Dict[str, str]:
    """Load the global extension-to-language mapping using config hierarchy.
    
    Uses the same multi-level config system as the main config loader:
    1. Repo-specific config (if in a repo)
    2. User config (~/.dolphin/config.toml, auto-created)
    3. Built-in template
    
    This is cached since the config file rarely changes during a session.
    Returns an empty map if no [languages] section is found.
    """
    try:
        # Import TOML library (Python 3.11+ has tomllib, else use tomli)
        try:
            import tomllib  # type: ignore[import-untyped, import-not-found]
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[import-not-found, no-redef]
            except ImportError:
                _log.warning("No TOML library (tomli) available. Language detection will be disabled.")
                return {}
        
        from pathlib import Path as PathLib
        
        # Try user config first (will be auto-created if missing)
        user_config_path = PathLib.home() / ".dolphin" / "config.toml"
        
        # Auto-create user config if it doesn't exist
        if not user_config_path.exists():
            _log.info("User config not found, creating from template")
            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Read bundled template
            template_path = PathLib(__file__).parent.parent / "config_template.toml"
            if template_path.exists():
                template_content = template_path.read_text(encoding="utf-8")
                user_config_path.write_text(template_content, encoding="utf-8")
                _log.info("Created user config at %s", user_config_path)
            else:
                _log.warning("Config template not found at %s", template_path)
                return {}
        
        # Load the config
        config_path = user_config_path
        _log.debug("Loading language mappings from: %s", config_path)
        
        with config_path.open("rb") as f:
            data = tomllib.load(f)
        
        lang_section = data.get("languages", {})
        if not lang_section:
            _log.warning("No [languages] section in config at %s", config_path)
            return {}
        
        # Build extension map from config
        ext_map = {}
        for ext, lang in lang_section.items():
            if isinstance(ext, str) and isinstance(lang, str):
                ext_map[ext.lower()] = lang.lower()
        
        _log.info("Loaded %d extension mappings from %s", len(ext_map), config_path)
        return ext_map
        
    except Exception as e:
        _log.warning("Failed to load extension mappings: %s. Language detection will be disabled.", e)
        return {}


def detect_language_from_extension(file_path: Path) -> Optional[str]:
    """Detect language identifier from file extension.
    
    Args:
        file_path: Path to the file (can be relative or absolute)
        
    Returns:
        Language identifier (e.g., "python", "typescript") or None if unknown
        
    Example:
        >>> detect_language_from_extension(Path("src/main.py"))
        "python"
        >>> detect_language_from_extension(Path("app.tsx"))
        "typescriptreact"
    """
    ext = file_path.suffix.lstrip(".").lower()
    if not ext:
        return None
    
    # Try to load from config first
    ext_map = _load_global_extension_map()
    if ext_map:
        result = ext_map.get(ext)
        if result:
            return result
    
    # Fallback to hardcoded mappings from kb.ingest.lang
    from ..ingest.lang import classify_language
    _, language = classify_language(file_path)
    
    # classify_language returns "text" as default, we return None for unknown
    return language if language != "text" else None


def get_chunker_for_file(file_path: Path) -> Optional[ChunkerFunction]:
    """Get the appropriate chunker for a file based on its extension.
    
    Args:
        file_path: Path to the file (can be relative or absolute)
        
    Returns:
        A chunker function if the language is known, otherwise None.
    """
    language = detect_language_from_extension(file_path)
    if language is None:
        return None
    return get_chunker(language)


def get_chunker(language: str) -> ChunkerFunction:
    """Get the appropriate chunker function for a given language.
    
    Routes to specialized chunkers when available (Python, TypeScript, Markdown),
    otherwise returns the fallback token-windowing chunker.
    
    Args:
        language: Language identifier (e.g., "python", "typescript", "markdown")
        
    Returns:
        A chunker function that accepts (text, model, token_target, overlap_pct)
        and returns a list of Chunk objects.
        
    Example:
        >>> chunker = get_chunker("python")
        >>> chunks = chunker(source_code, model="small", token_target=400)
    """
    lang_key = language.lower() if language else "text"
    
    # Return specialized chunker if available
    if lang_key in _BUILTIN_CHUNKERS:
        _log.debug("Using specialized chunker for language: %s", lang_key)
        return _BUILTIN_CHUNKERS[lang_key]
    
    # Fallback to generic token windowing
    _log.debug("Using fallback chunker for language: %s", lang_key)
    return chunk_text


def chunk_file(
    *,
    abs_path: Path,
    rel_path: str,
    language: str,
    text: str,
    repo_config: RepoChunkingConfig,
    token_target: Optional[int] = None,
    overlap_pct: Optional[float] = None,
) -> List:  # Returns list of Chunk objects
    """High-level interface for chunking a file with repository configuration.
    
    This is the primary entry point for chunking files in the knowledge base pipeline.
    It automatically:
    - Selects the appropriate chunker based on language
    - Applies per-language token window sizes from repo config
    - Uses the configured embedding model for tokenization
    - Attaches symbol_path metadata using rel_path
    
    Args:
        abs_path: Absolute path to the file (for logging/debugging)
        rel_path: Relative path from repository root (used in symbol_path)
        language: Language identifier (from detect_language_from_extension)
        text: File content to chunk
        repo_config: Repository chunking configuration
        token_target: Override token window size (uses config if None)
        overlap_pct: Override overlap percentage (uses config if None)
        
    Returns:
        List of Chunk objects with provenance and metadata
        
    Example:
        >>> config = load_repo_chunking_config(Path("/path/to/repo"))
        >>> chunks = chunk_file(
        ...     abs_path=Path("/path/to/repo/src/main.py"),
        ...     rel_path="src/main.py",
        ...     language="python",
        ...     text=source_code,
        ...     repo_config=config,
        ... )
    """
    # Resolve token target and overlap from config
    if token_target is None:
        token_target = repo_config.get_window_size_for_language(language)
    
    if overlap_pct is None:
        overlap_pct = repo_config.overlap_pct
    
    # Map embedding model to tokenizer model name
    # "text-embedding-3-small" -> "small", "text-embedding-3-large" -> "large"
    model = "small"  # Default
    if repo_config.embedding_model:
        if "large" in repo_config.embedding_model.lower():
            model = "large"
        elif "small" in repo_config.embedding_model.lower():
            model = "small"
    
    # Get the appropriate chunker
    chunker = get_chunker(language)
    
    _log.debug(
        "Chunking %s (lang=%s, model=%s, target=%d, overlap=%.2f)",
        rel_path,
        language,
        model,
        token_target,
        overlap_pct,
    )
    
    # Execute chunking
    try:
        chunks = chunker(
            text,
            model=model,
            token_target=token_target,
            overlap_pct=overlap_pct,
        )
    except Exception as e:
        _log.error("Chunker failed for %s: %s. Using fallback.", rel_path, e)
        chunks = chunk_text(
            text,
            model=model,
            token_target=token_target,
            overlap_pct=overlap_pct,
        )
    
    # Post-process: attach or enhance symbol_path with rel_path
    enriched_chunks = []
    for chunk in chunks:
        # If chunk already has a symbol_path, prepend rel_path if needed
        if chunk.symbol_path and not chunk.symbol_path.startswith(rel_path):
            # Format: "rel_path:symbol_path"
            symbol_path = f"{rel_path}:{chunk.symbol_path}"
        elif chunk.symbol_path:
            symbol_path = chunk.symbol_path
        else:
            # No symbol, just use rel_path as identifier
            symbol_path = rel_path
        
        # Create new Chunk with updated symbol_path
        enriched_chunk = Chunk(
            text=chunk.text,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            token_count=chunk.token_count,
            symbol_kind=chunk.symbol_kind,
            symbol_name=chunk.symbol_name,
            symbol_path=symbol_path,
            h1=chunk.h1,
            h2=chunk.h2,
            h3=chunk.h3,
        )
        enriched_chunks.append(enriched_chunk)
    
    _log.info(
        "Chunked %s into %d chunks (avg %d tokens)",
        rel_path,
        len(enriched_chunks),
        sum(c.token_count for c in enriched_chunks) // len(enriched_chunks)
        if enriched_chunks
        else 0,
    )
    
    return enriched_chunks
