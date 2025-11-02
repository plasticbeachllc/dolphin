from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

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
class KBConfig:
    """Runtime configuration for the knowledge store components."""

    store_root: Path = field(default_factory=lambda: _to_path(CONFIG_ROOT))
    endpoint: str = "127.0.0.1:7777"
    default_embed_model: str = "large"
    concurrency: int = 3
    per_session_spend_cap_usd: float = 10.0
    ignore: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS))
    score_cutoff: float = 0.15
    top_k: int = 8
    max_snippet_tokens: int = 240
    # Embedding provider configuration
    embedding_provider: str = "stub"  # 'stub' or 'openai'
    embedding_batch_size: int = 100
    openai_api_key_env: str = "OPENAI_API_KEY"
    # Cache configuration
    cache_enabled: bool = True
    redis_url: str | None = None  # e.g., "redis://localhost:6379/0"
    embedding_cache_ttl: int = 3600  # 1 hour
    result_cache_ttl: int = 900  # 15 minutes

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KBConfig":
        """Create a configuration object from a mapping."""
        ignore_values = data.get("ignore") or DEFAULT_IGNORE_PATTERNS
        retrieval = data.get("retrieval") or {}
        embedding = data.get("embedding") or {}
        cache = data.get("cache") or {}
        return cls(
            store_root=_to_path(data.get("store_root", CONFIG_ROOT)),
            endpoint=str(data.get("endpoint", "127.0.0.1:7777")),
            default_embed_model=str(
                embedding.get("default_embed_model",
                             data.get("default_embed_model", "small"))
            ),
            concurrency=int(
                embedding.get("concurrency",
                             data.get("concurrency", 3))
            ),
            per_session_spend_cap_usd=float(
                embedding.get("per_session_spend_cap_usd",
                             data.get("per_session_spend_cap_usd", 10.0))
            ),
            ignore=list(ignore_values),
            score_cutoff=float(
                retrieval.get("score_cutoff", data.get("score_cutoff", 0.15))
            ),
            top_k=int(retrieval.get("top_k", data.get("top_k", 8))),
            max_snippet_tokens=int(
                retrieval.get("max_snippet_tokens", data.get("max_snippet_tokens", 240))
            ),
            embedding_provider=str(
                embedding.get("provider", data.get("embedding_provider", "stub"))
            ),
            embedding_batch_size=int(
                embedding.get("batch_size", data.get("embedding_batch_size", 100))
            ),
            openai_api_key_env=str(
                embedding.get("api_key_env", data.get("openai_api_key_env", "OPENAI_API_KEY"))
            ),
            cache_enabled=bool(
                cache.get("enabled", data.get("cache_enabled", True))
            ),
            redis_url=cache.get("redis_url", data.get("redis_url")),
            embedding_cache_ttl=int(
                cache.get("embedding_ttl", data.get("embedding_cache_ttl", 3600))
            ),
            result_cache_ttl=int(
                cache.get("result_ttl", data.get("result_cache_ttl", 900))
            ),
        )

    def resolved_store_root(self) -> Path:
        """Return the absolute path to the store root."""
        return _to_path(self.store_root)


def load_config(path: Path | None = None, repo_path: Path | None = None) -> KBConfig:
    """Load configuration with multi-level hierarchy.
    
    Priority order (highest to lowest):
    1. Explicitly provided path (if exists, otherwise use defaults - no auto-create)
    2. Repo-specific config (./.dolphin/config.toml)
    3. User config (~/.dolphin/config.toml, auto-created if missing)
    4. Built-in defaults
    
    Args:
        path: Explicit config file path (highest priority, won't auto-create)
        repo_path: Path to repository root for repo-specific config lookup
        
    Returns:
        KBConfig instance with merged configuration
    """
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
        return KBConfig()
    
    if not isinstance(config_data, Mapping):
        raise ValueError(f"Config must contain a mapping")
    
    return KBConfig.from_mapping(config_data)
