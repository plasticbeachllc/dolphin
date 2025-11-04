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
    mmr_enabled: bool = True
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
        
        # Extract nested sections, falling back to empty dicts
        retrieval_data = data.get("retrieval", {})
        reranking_data = retrieval_data.get("reranking", {}) if isinstance(retrieval_data, dict) else {}
        hybrid_search_data = retrieval_data.get("hybrid_search", {}) if isinstance(retrieval_data, dict) else {}
        ann_data = retrieval_data.get("ann", {}) if isinstance(retrieval_data, dict) else {}
        embedding_data = data.get("embedding", {})
        cache_data = data.get("cache", {})
        storage_data = data.get("storage", {})
        server_data = data.get("server", {})

        # Type coercion for optional fields
        def _coerce_optional(value, target_type):
            if value is None:
                return None
            try:
                if target_type is bool and isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return target_type(value)
            except (ValueError, TypeError):
                return value  # Keep original if coercion fails

        # Build nested dataclasses with proper defaults for missing values
        reranking_config = RerankingConfig()
        if reranking_data:
            if "enabled" in reranking_data:
                reranking_config.enabled = _coerce_optional(reranking_data.get("enabled"), bool)
            if "model" in reranking_data:
                reranking_config.model = reranking_data.get("model")
            if "device" in reranking_data:
                reranking_config.device = reranking_data.get("device")
            if "batch_size" in reranking_data:
                reranking_config.batch_size = _coerce_optional(reranking_data.get("batch_size"), int)
            if "candidate_multiplier" in reranking_data:
                reranking_config.candidate_multiplier = _coerce_optional(reranking_data.get("candidate_multiplier"), int)
            if "score_threshold" in reranking_data:
                reranking_config.score_threshold = _coerce_optional(reranking_data.get("score_threshold"), float)

        hybrid_search_config = HybridSearchConfig()
        if hybrid_search_data:
            if "enabled" in hybrid_search_data:
                hybrid_search_config.enabled = _coerce_optional(hybrid_search_data.get("enabled"), bool)
            if "fusion_method" in hybrid_search_data:
                hybrid_search_config.fusion_method = hybrid_search_data.get("fusion_method")
            if "fusion_k" in hybrid_search_data:
                hybrid_search_config.fusion_k = _coerce_optional(hybrid_search_data.get("fusion_k"), int)

        ann_config = ANNConfig()
        if ann_data:
            if "strategy" in ann_data:
                ann_config.strategy = ann_data.get("strategy")
            if "metric" in ann_data:
                ann_config.metric = ann_data.get("metric")
            if "estimated_dataset_size" in ann_data:
                ann_config.estimated_dataset_size = _coerce_optional(ann_data.get("estimated_dataset_size"), int)
            if "default_query_type" in ann_data:
                ann_config.default_query_type = ann_data.get("default_query_type")

        retrieval_config = RetrievalConfig(
            reranking=reranking_config,
            hybrid_search=hybrid_search_config,
            ann=ann_config
        )
        if retrieval_data:
            if "score_cutoff" in retrieval_data:
                retrieval_config.score_cutoff = _coerce_optional(retrieval_data.get("score_cutoff"), float)
            if "top_k" in retrieval_data:
                retrieval_config.top_k = _coerce_optional(retrieval_data.get("top_k"), int)
            if "max_snippet_tokens" in retrieval_data:
                retrieval_config.max_snippet_tokens = _coerce_optional(retrieval_data.get("max_snippet_tokens"), int)
            if "mmr_enabled" in retrieval_data:
                retrieval_config.mmr_enabled = _coerce_optional(retrieval_data.get("mmr_enabled"), bool)
            if "mmr_lambda" in retrieval_data:
                retrieval_config.mmr_lambda = _coerce_optional(retrieval_data.get("mmr_lambda"), float)

        # Build top-level config with proper defaults
        config_kwargs = {}
        
        # Handle storage settings
        if storage_data and storage_data.get("store_root"):
            config_kwargs['store_root'] = _to_path(storage_data.get("store_root"))
            
        # Handle server settings
        if server_data and server_data.get("endpoint"):
            config_kwargs['endpoint'] = server_data.get("endpoint")
            
        # Handle embedding settings
        if embedding_data:
            if embedding_data.get("default_embed_model"):
                config_kwargs['default_embed_model'] = embedding_data.get("default_embed_model")
            if embedding_data.get("concurrency") is not None:
                config_kwargs['concurrency'] = _coerce_optional(embedding_data.get("concurrency"), int)
            if embedding_data.get("provider"):
                config_kwargs['embedding_provider'] = embedding_data.get("provider")
            if embedding_data.get("batch_size") is not None:
                config_kwargs['embedding_batch_size'] = _coerce_optional(embedding_data.get("batch_size"), int)
            if embedding_data.get("api_key_env"):
                config_kwargs['openai_api_key_env'] = embedding_data.get("api_key_env")
                
        # Handle top-level settings
        if data.get("per_session_spend_cap_usd") is not None:
            config_kwargs['per_session_spend_cap_usd'] = _coerce_optional(data.get("per_session_spend_cap_usd"), float)
        if data.get("ignore"):
            config_kwargs['ignore'] = data.get("ignore")
        if data.get("exceptions") or data.get("ignore_exceptions"):
            config_kwargs['ignore_exceptions'] = data.get("exceptions", data.get("ignore_exceptions", []))
            
        # Always override retrieval config with our constructed one
        config_kwargs['retrieval'] = retrieval_config
        
        # Handle cache settings
        if cache_data:
            if cache_data.get("enabled") is not None:
                config_kwargs['cache_enabled'] = _coerce_optional(cache_data.get("enabled"), bool)
            if cache_data.get("redis_url"):
                config_kwargs['redis_url'] = cache_data.get("redis_url")
            if cache_data.get("embedding_ttl") is not None:
                config_kwargs['embedding_cache_ttl'] = _coerce_optional(cache_data.get("embedding_ttl"), int)
            if cache_data.get("result_ttl") is not None:
                config_kwargs['result_cache_ttl'] = _coerce_optional(cache_data.get("result_ttl"), int)

        return cls(**config_kwargs)

    def resolved_store_root(self) -> Path:
        """Return the absolute path to the store root."""
        return _to_path(self.store_root)


def load_config(path: Path | None = None, repo_path: Path | None = None) -> KBConfig:
    """Load configuration strictly from file (no in-code fallbacks or env overrides).

    Resolution order (highest to lowest):
    1. Explicit path (must exist)
    2. Repo-specific config at ./.dolphin/config.toml (when repo_path is provided)
    3. User config at ~/.dolphin/config.toml (must exist)

    Raises:
        FileNotFoundError: when no configuration file is found.
        ValueError: when the loaded file is not a TOML mapping.
    """
    config_data: dict[str, Any] = {}

    # 1) Explicit path
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Config not found at {path}. Run 'dolphin init' to create one.")
        _log.debug("Loading config from explicit path: %s", path)
        with path.open("rb") as f:
            config_data = tomllib.load(f) or {}

    # 2) Repo-specific config
    elif repo_path:
        repo_config_path = repo_path / ".dolphin" / "config.toml"
        if repo_config_path.exists():
            _log.debug("Loading repo config: %s", repo_config_path)
            with repo_config_path.open("rb") as f:
                config_data = tomllib.load(f) or {}

    # 3) User config
    if not config_data and path is None:
        user_config = USER_CONFIG_PATH
        if not user_config.exists():
            raise FileNotFoundError("No configuration found. Create one with 'dolphin init' or provide --config path.")
        _log.debug("Loading user config: %s", user_config)
        with user_config.open("rb") as f:
            config_data = tomllib.load(f) or {}

    if not isinstance(config_data, Mapping):
        raise ValueError("Config must contain a mapping at the top level")

    return KBConfig.from_mapping(config_data)
