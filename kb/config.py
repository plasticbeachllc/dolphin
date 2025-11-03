from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .ignores import DEFAULT_IGNORE_PATTERNS

_log = logging.getLogger(__name__)

CONFIG_ROOT = Path.home() / ".dolphin" / "knowledge_store"
DEFAULT_CONFIG_PATH = CONFIG_ROOT / "config.toml"
USER_CONFIG_PATH = Path.home() / ".dolphin" / "config.toml"

# Path to the bundled config template
_TEMPLATE_PATH = Path(__file__).parent / "config_template.toml"


def _to_path(value: Any) -> Path:
    if isinstance(value, Path):
        return value.expanduser().resolve()
    return Path(str(value)).expanduser().resolve()


def _read_template() -> str:
    """Read the bundled config template."""
    if _TEMPLATE_PATH.exists():
        return _TEMPLATE_PATH.read_text(encoding="utf-8")
    _log.warning("Config template not found at %s", _TEMPLATE_PATH)
    return ""


def _ensure_user_config() -> Path:
    """Ensure user config exists, creating it from template if needed.
    
    Returns the path to the user config file.
    """
    config_path = USER_CONFIG_PATH
    
    if not config_path.exists():
        _log.info("Creating user config at %s", config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        template = _read_template()
        if template:
            config_path.write_text(template, encoding="utf-8")
            _log.info("User config created successfully")
        else:
            _log.warning("Could not create user config: template not available")
    
    return config_path


@dataclass
class RerankingConfig:
    enabled: bool = False
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    device: Optional[str] = None
    batch_size: int = 32
    candidate_multiplier: int = 4
    score_threshold: float = 0.3

@dataclass
class HybridSearchConfig:
    enabled: bool = True
    fusion_method: str = "rrf"
    fusion_k: int = 60

@dataclass
class ANNConfig:
    strategy: str = "adaptive"
    metric: str = "cosine"
    estimated_dataset_size: int = 100000
    default_query_type: str = "concept"

@dataclass
class RetrievalConfig:
    reranking: RerankingConfig = field(default_factory=RerankingConfig)
    hybrid_search: HybridSearchConfig = field(default_factory=HybridSearchConfig)
    ann: ANNConfig = field(default_factory=ANNConfig)
    score_cutoff: float = 0.15
    top_k: int = 8
    max_snippet_tokens: int = 240
    mmr_enabled: bool = False
    mmr_lambda: float = 0.7

@dataclass
class KBConfig:
    """Runtime configuration for the knowledge store components."""

    store_root: Path = field(default_factory=lambda: _to_path(CONFIG_ROOT))
    endpoint: str = "127.0.0.1:7777"
    default_embed_model: str = "large"
    concurrency: int = 3
    per_session_spend_cap_usd: float = 10.0
    ignore: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS))
    ignore_exceptions: list[str] = field(default_factory=list)
    
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    
    embedding_provider: str = "stub"
    embedding_batch_size: int = 100
    openai_api_key_env: str = "OPENAI_API_KEY"
    cache_enabled: bool = True
    redis_url: str | None = None
    embedding_cache_ttl: int = 3600
    result_cache_ttl: int = 900

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KBConfig":
        """Create a configuration object from a mapping, handling nested sections."""
        
        def _get_value(source, key, default, target_type):
            value = source.get(key, default)
            if value is None:
                return None
            try:
                if target_type is bool and isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return target_type(value)
            except (ValueError, TypeError):
                return default

        # Extract nested sections, falling back to empty dicts
        retrieval_data = data.get("retrieval", {})
        reranking_data = retrieval_data.get("reranking", {}) if isinstance(retrieval_data, dict) else {}
        hybrid_search_data = retrieval_data.get("hybrid_search", {}) if isinstance(retrieval_data, dict) else {}
        ann_data = retrieval_data.get("ann", {}) if isinstance(retrieval_data, dict) else {}
        embedding_data = data.get("embedding", {})
        cache_data = data.get("cache", {})

        # Build nested dataclasses first
        reranking_config = RerankingConfig(
            enabled=_get_value(reranking_data, "enabled", False, bool),
            model=_get_value(reranking_data, "model", "cross-encoder/ms-marco-MiniLM-L-6-v2", str),
            device=_get_value(reranking_data, "device", None, str),
            batch_size=_get_value(reranking_data, "batch_size", 32, int),
            candidate_multiplier=_get_value(reranking_data, "candidate_multiplier", 4, int),
            score_threshold=_get_value(reranking_data, "score_threshold", 0.3, float)
        )
        
        hybrid_search_config = HybridSearchConfig(
            enabled=_get_value(hybrid_search_data, "enabled", True, bool),
            fusion_method=_get_value(hybrid_search_data, "fusion_method", "rrf", str),
            fusion_k=_get_value(hybrid_search_data, "fusion_k", 60, int)
        )
        
        ann_config = ANNConfig(
            strategy=_get_value(ann_data, "strategy", "adaptive", str),
            metric=_get_value(ann_data, "metric", "cosine", str),
            estimated_dataset_size=_get_value(ann_data, "estimated_dataset_size", 100000, int),
            default_query_type=_get_value(ann_data, "default_query_type", "concept", str)
        )
        
        retrieval_config = RetrievalConfig(
            reranking=reranking_config,
            hybrid_search=hybrid_search_config,
            ann=ann_config,
            score_cutoff=_get_value(retrieval_data, "score_cutoff", 0.15, float),
            top_k=_get_value(retrieval_data, "top_k", 8, int),
            max_snippet_tokens=_get_value(retrieval_data, "max_snippet_tokens", 240, int),
            mmr_enabled=_get_value(retrieval_data, "mmr_enabled", False, bool),
            mmr_lambda=_get_value(retrieval_data, "mmr_lambda", 0.7, float)
        )

        return cls(
            store_root=_to_path(data.get("store_root", CONFIG_ROOT)),
            endpoint=_get_value(data, "endpoint", "127.0.0.1:7777", str),
            default_embed_model=_get_value(embedding_data, "default_embed_model", "large", str),
            concurrency=_get_value(embedding_data, "concurrency", 3, int),
            per_session_spend_cap_usd=_get_value(data, "per_session_spend_cap_usd", 10.0, float),
            ignore=data.get("ignore", DEFAULT_IGNORE_PATTERNS),
            ignore_exceptions=data.get("exceptions", data.get("ignore_exceptions", [])),
            retrieval=retrieval_config,
            embedding_provider=_get_value(embedding_data, "provider", "stub", str),
            embedding_batch_size=_get_value(embedding_data, "batch_size", 100, int),
            openai_api_key_env=_get_value(embedding_data, "api_key_env", "OPENAI_API_KEY", str),
            cache_enabled=_get_value(cache_data, "enabled", True, bool),
            redis_url=_get_value(cache_data, "redis_url", None, str),
            embedding_cache_ttl=_get_value(cache_data, "embedding_ttl", 3600, int),
            result_cache_ttl=_get_value(cache_data, "result_ttl", 900, int),
        )

    def resolved_store_root(self) -> Path:
        """Return the absolute path to the store root."""
        return _to_path(self.store_root)


def load_config(path: Path | None = None, repo_path: Path | None = None) -> KBConfig:
    """Load configuration with multi-level hierarchy.
    
    Priority order (highest to lowest):
    1. DOLPHIN_STORE_ROOT environment variable (overrides store_root only)
    2. Explicitly provided path (if exists, otherwise use defaults - no auto-create)
    3. Repo-specific config (./.dolphin/config.toml)
    4. User config (~/.dolphin/config.toml, auto-created if missing)
    5. Built-in defaults
    
    Args:
        path: Explicit config file path (highest priority, won't auto-create)
        repo_path: Path to repository root for repo-specific config lookup
        
    Returns:
        KBConfig instance with merged configuration
    """
    import os
    
    config_data: dict[str, Any] = {}
    
    # Try explicit path first - if provided but doesn't exist, return defaults (no auto-create)
    if path is not None:
        if path.exists():
            _log.debug("Loading config from explicit path: %s", path)
            with path.open("rb") as f:
                config_data = tomllib.load(f) or {}
        else:
            _log.debug("Explicit path %s doesn't exist, using defaults", path)
            return KBConfig()
    
    # Try repo-specific config
    elif repo_path:
        repo_config_path = repo_path / ".dolphin" / "config.toml"
        if repo_config_path.exists():
            _log.debug("Loading repo config: %s", repo_config_path)
            with repo_config_path.open("rb") as f:
                config_data = tomllib.load(f) or {}
        else:
            # Fall through to user config
            _log.debug("No repo config at %s, trying user config", repo_config_path)
    
    # If no explicit path and no config loaded yet, try user config (auto-create if needed)
    if not config_data and path is None:
        user_config = _ensure_user_config()
        if user_config.exists():
            _log.debug("Loading user config: %s", user_config)
            with user_config.open("rb") as f:
                config_data = tomllib.load(f) or {}
    
    # If still no config, use defaults
    if not config_data:
        _log.debug("No config found, using built-in defaults")
        config_data = {}
    
    if config_data and not isinstance(config_data, Mapping):
        raise ValueError(f"Config must contain a mapping")
    
    # Apply environment variable overrides BEFORE creating KBConfig
    # This ensures DOLPHIN_STORE_ROOT takes precedence
    env_store_root = os.environ.get("DOLPHIN_STORE_ROOT")
    if env_store_root:
        _log.debug("Overriding store_root with DOLPHIN_STORE_ROOT: %s", env_store_root)
        config_data["store_root"] = env_store_root
    
    return KBConfig.from_mapping(config_data)
