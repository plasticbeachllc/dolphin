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
        storage_data = data.get("storage", {})
        server_data = data.get("server", {})

        # Type coercion for nested fields
        def _coerce_optional(value, target_type):
            if value is None:
                return None
            try:
                if target_type is bool and isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return target_type(value)
            except (ValueError, TypeError):
                return value  # Keep original if coercion fails

        # Build nested dataclasses first - all values must come from config file
        reranking_config = RerankingConfig(
            enabled=_coerce_optional(reranking_data.get("enabled"), bool),
            model=reranking_data.get("model"),
            device=reranking_data.get("device"),
            batch_size=_coerce_optional(reranking_data.get("batch_size"), int),
            candidate_multiplier=_coerce_optional(reranking_data.get("candidate_multiplier"), int),
            score_threshold=_coerce_optional(reranking_data.get("score_threshold"), float)
        )

        hybrid_search_config = HybridSearchConfig(
            enabled=_coerce_optional(hybrid_search_data.get("enabled"), bool),
            fusion_method=hybrid_search_data.get("fusion_method"),
            fusion_k=_coerce_optional(hybrid_search_data.get("fusion_k"), int)
        )

        ann_config = ANNConfig(
            strategy=ann_data.get("strategy"),
            metric=ann_data.get("metric"),
            estimated_dataset_size=_coerce_optional(ann_data.get("estimated_dataset_size"), int),
            default_query_type=ann_data.get("default_query_type")
        )

        retrieval_config = RetrievalConfig(
            reranking=reranking_config,
            hybrid_search=hybrid_search_config,
            ann=ann_config,
            score_cutoff=_coerce_optional(retrieval_data.get("score_cutoff"), float),
            top_k=_coerce_optional(retrieval_data.get("top_k"), int),
            max_snippet_tokens=_coerce_optional(retrieval_data.get("max_snippet_tokens"), int),
            mmr_enabled=_coerce_optional(retrieval_data.get("mmr_enabled"), bool),
            mmr_lambda=_coerce_optional(retrieval_data.get("mmr_lambda"), float)
        )

        # Derive required top-level values strictly from config file (no in-code fallbacks)
        store_root_value = None
        if isinstance(storage_data, dict):
            store_root_value = storage_data.get("store_root")
        endpoint_value = None
        if isinstance(server_data, dict):
            endpoint_value = server_data.get("endpoint")

        # Strict validation of all required keys (no in-code fallbacks)
        missing: list[str] = []
        if not store_root_value:
            missing.append("storage.store_root")
        if not endpoint_value:
            missing.append("server.endpoint")
        if not isinstance(embedding_data, dict) or embedding_data.get("provider") is None:
            missing.append("embedding.provider")
        if not isinstance(embedding_data, dict) or embedding_data.get("default_embed_model") is None:
            missing.append("embedding.default_embed_model")

        # Validate all retrieval/ANN/reranking fields are present
        if not isinstance(retrieval_data, dict):
            missing.append("retrieval section")
        else:
            if retrieval_data.get("score_cutoff") is None:
                missing.append("retrieval.score_cutoff")
            if retrieval_data.get("top_k") is None:
                missing.append("retrieval.top_k")
            if retrieval_data.get("max_snippet_tokens") is None:
                missing.append("retrieval.max_snippet_tokens")
            if retrieval_data.get("mmr_enabled") is None:
                missing.append("retrieval.mmr_enabled")
            if retrieval_data.get("mmr_lambda") is None:
                missing.append("retrieval.mmr_lambda")

            # Validate nested sections
            if not isinstance(reranking_data, dict):
                missing.append("retrieval.reranking section")
            else:
                for key in ["enabled", "model", "batch_size", "candidate_multiplier", "score_threshold"]:
                    if reranking_data.get(key) is None:
                        missing.append(f"retrieval.reranking.{key}")

            if not isinstance(hybrid_search_data, dict):
                missing.append("retrieval.hybrid_search section")
            else:
                for key in ["enabled", "fusion_method", "fusion_k"]:
                    if hybrid_search_data.get(key) is None:
                        missing.append(f"retrieval.hybrid_search.{key}")

            if not isinstance(ann_data, dict):
                missing.append("retrieval.ann section")
            else:
                for key in ["strategy", "metric", "estimated_dataset_size", "default_query_type"]:
                    if ann_data.get(key) is None:
                        missing.append(f"retrieval.ann.{key}")

        if missing:
            raise ValueError("Missing required configuration in ~/.dolphin/config.toml: " + ", ".join(missing))

        # Type coercion for optional fields that have values
        def _coerce_optional(value, target_type):
            if value is None:
                return None
            try:
                if target_type is bool and isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return target_type(value)
            except (ValueError, TypeError):
                return value  # Keep original if coercion fails

        return cls(
            store_root=_to_path(store_root_value),
            endpoint=str(endpoint_value),
            default_embed_model=embedding_data.get("default_embed_model"),
            concurrency=_coerce_optional(embedding_data.get("concurrency"), int),
            per_session_spend_cap_usd=_coerce_optional(data.get("per_session_spend_cap_usd"), float),
            ignore=data.get("ignore", DEFAULT_IGNORE_PATTERNS),
            ignore_exceptions=data.get("exceptions", data.get("ignore_exceptions", [])),
            retrieval=retrieval_config,
            embedding_provider=embedding_data.get("provider"),
            embedding_batch_size=_coerce_optional(embedding_data.get("batch_size"), int),
            openai_api_key_env=embedding_data.get("api_key_env"),
            cache_enabled=_coerce_optional(cache_data.get("enabled"), bool),
            redis_url=cache_data.get("redis_url"),
            embedding_cache_ttl=_coerce_optional(cache_data.get("embedding_ttl"), int),
            result_cache_ttl=_coerce_optional(cache_data.get("result_ttl"), int),
        )

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
