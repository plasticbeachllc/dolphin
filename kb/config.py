from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .ignores import DEFAULT_IGNORE_PATTERNS

_log = logging.getLogger(__name__)


class ConfigNotFoundError(FileNotFoundError):
    """Raised when no Dolphin configuration file can be located."""


CONFIG_ROOT = Path.home() / ".dolphin" / "knowledge_store"
USER_CONFIG_PATH = Path.home() / ".dolphin" / "config.toml"
DEFAULT_CONFIG_PATH = USER_CONFIG_PATH

# Path to the bundled config template
_TEMPLATE_PATH = Path(__file__).parent / "config_template.toml"


def _to_path(value: Any, base_dir: Path | None = None) -> Path:
    if isinstance(value, Path):
        path = value
    else:
        path = Path(str(value))

    path = path.expanduser()

    if base_dir and not path.is_absolute():
        path = base_dir / path

    return path.resolve()


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
    device: str | None = None
    batch_size: int = 32
    candidate_multiplier: int = 4
    score_threshold: float = 0.3


@dataclass
class HybridSearchConfig:
    enabled: bool = True
    fusion_method: str = "rrf"
    fusion_k: int = 60


@dataclass
class BM25NormalizationRuntimeConfig:
    strategy: str = "sigmoid"
    stats_path: str | None = None
    fallback_strategy: str = "sigmoid"
    ab_variant_probability: float = 0.0


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
    bm25_normalization: BM25NormalizationRuntimeConfig = field(default_factory=BM25NormalizationRuntimeConfig)


@dataclass
class ApiConfig:
    max_top_k: int = 100
    max_snippet_tokens: int = 1000
    max_context_lines: int = 10
    include_graph_context: bool = True
    context_lines_before: int = 0
    context_lines_after: int = 0


@dataclass
class GraphConfig:
    max_related_nodes: int = 10
    max_edges_per_node: int = 5


@dataclass
class KBConfig:
    """Runtime configuration for the knowledge store components."""

    store_root: Path = field(default_factory=lambda: _to_path(CONFIG_ROOT))
    endpoint: str = "127.0.0.1:7777"
    default_embed_model: str = "small"
    concurrency: int = 3
    per_session_spend_cap_usd: float = 10.0
    ignore: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS))
    ignore_exceptions: list[str] = field(default_factory=list)

    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)

    embedding_provider: str = "stub"
    embedding_batch_size: int = 100
    openai_api_key_env: str = "OPENAI_API_KEY"
    cache_enabled: bool = True
    redis_url: str | None = None
    embedding_cache_ttl: int = 3600
    result_cache_ttl: int = 900

    @staticmethod
    def _coerce_optional(value: Any, target_type: type) -> Any:
        """Coerce a value to target type, handling None and string booleans."""
        if value is None:
            return None
        try:
            if target_type is bool and isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return target_type(value)
        except (ValueError, TypeError):
            return value  # Keep original if coercion fails

    @classmethod
    def _build_reranking_config(cls, data: dict) -> RerankingConfig:
        """Build reranking configuration from mapping."""
        config = RerankingConfig()
        if not data:
            return config

        if "enabled" in data:
            config.enabled = cls._coerce_optional(data["enabled"], bool)
        if "model" in data:
            config.model = data["model"]
        if "device" in data:
            config.device = data["device"]
        if "batch_size" in data:
            config.batch_size = cls._coerce_optional(data["batch_size"], int)
        if "candidate_multiplier" in data:
            config.candidate_multiplier = cls._coerce_optional(data["candidate_multiplier"], int)
        if "score_threshold" in data:
            config.score_threshold = cls._coerce_optional(data["score_threshold"], float)

        return config

    @classmethod
    def _build_hybrid_search_config(cls, data: dict) -> HybridSearchConfig:
        """Build hybrid search configuration from mapping."""
        config = HybridSearchConfig()
        if not data:
            return config

        if "enabled" in data:
            config.enabled = cls._coerce_optional(data["enabled"], bool)
        if "fusion_method" in data:
            config.fusion_method = data["fusion_method"]
        if "fusion_k" in data:
            config.fusion_k = cls._coerce_optional(data["fusion_k"], int)

        return config

    @classmethod
    def _build_ann_config(cls, data: dict) -> ANNConfig:
        """Build ANN configuration from mapping."""
        config = ANNConfig()
        if not data:
            return config

        if "strategy" in data:
            config.strategy = data["strategy"]
        if "metric" in data:
            config.metric = data["metric"]
        if "estimated_dataset_size" in data:
            config.estimated_dataset_size = cls._coerce_optional(data["estimated_dataset_size"], int)
        if "default_query_type" in data:
            config.default_query_type = data["default_query_type"]

        return config

    @classmethod
    def _build_bm25_normalization_config(cls, data: dict) -> BM25NormalizationRuntimeConfig:
        """Build BM25 normalization configuration from mapping."""
        config = BM25NormalizationRuntimeConfig()
        if not data:
            return config

        if "strategy" in data:
            config.strategy = str(data["strategy"]).lower()
        if data.get("stats_path"):
            config.stats_path = str(data["stats_path"])
        if "fallback_strategy" in data:
            config.fallback_strategy = str(data["fallback_strategy"]).lower()
        if "ab_variant_probability" in data:
            config.ab_variant_probability = cls._coerce_optional(data["ab_variant_probability"], float)

        return config

    @classmethod
    def _build_api_config(cls, data: dict) -> ApiConfig:
        """Build API configuration from mapping."""
        config = ApiConfig()
        if not data:
            return config

        if "max_top_k" in data:
            config.max_top_k = cls._coerce_optional(data["max_top_k"], int)
        if "max_snippet_tokens" in data:
            config.max_snippet_tokens = cls._coerce_optional(data["max_snippet_tokens"], int)
        if "max_context_lines" in data:
            config.max_context_lines = cls._coerce_optional(data["max_context_lines"], int)
        if "include_graph_context" in data:
            config.include_graph_context = cls._coerce_optional(data["include_graph_context"], bool)
        if "context_lines_before" in data:
            config.context_lines_before = cls._coerce_optional(data["context_lines_before"], int)
        if "context_lines_after" in data:
            config.context_lines_after = cls._coerce_optional(data["context_lines_after"], int)

        return config

    @classmethod
    def _build_graph_config(cls, data: dict) -> GraphConfig:
        """Build graph configuration from mapping."""
        config = GraphConfig()
        if not data:
            return config

        if "max_related_nodes" in data:
            config.max_related_nodes = cls._coerce_optional(data["max_related_nodes"], int)
        if "max_edges_per_node" in data:
            config.max_edges_per_node = cls._coerce_optional(data["max_edges_per_node"], int)

        return config

    @classmethod
    def _build_retrieval_config(cls, data: dict) -> RetrievalConfig:
        """Build retrieval configuration from mapping."""
        reranking_data = data.get("reranking", {}) if isinstance(data, dict) else {}
        hybrid_search_data = data.get("hybrid_search", {}) if isinstance(data, dict) else {}
        ann_data = data.get("ann", {}) if isinstance(data, dict) else {}
        bm25_data = data.get("bm25_normalization", {}) if isinstance(data, dict) else {}

        config = RetrievalConfig(
            reranking=cls._build_reranking_config(reranking_data),
            hybrid_search=cls._build_hybrid_search_config(hybrid_search_data),
            ann=cls._build_ann_config(ann_data),
            bm25_normalization=cls._build_bm25_normalization_config(bm25_data),
        )

        if "score_cutoff" in data:
            config.score_cutoff = cls._coerce_optional(data["score_cutoff"], float)
        if "top_k" in data:
            config.top_k = cls._coerce_optional(data["top_k"], int)
        if "max_snippet_tokens" in data:
            config.max_snippet_tokens = cls._coerce_optional(data["max_snippet_tokens"], int)
        if "mmr_enabled" in data:
            config.mmr_enabled = cls._coerce_optional(data["mmr_enabled"], bool)
        if "mmr_lambda" in data:
            config.mmr_lambda = cls._coerce_optional(data["mmr_lambda"], float)

        return config

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], config_dir: Path | None = None) -> KBConfig:
        """Create a configuration object from a mapping, handling nested sections."""

        # Extract nested sections
        retrieval_data = data.get("retrieval", {})
        embedding_data = data.get("embedding", {})
        cache_data = data.get("cache", {})
        storage_data = data.get("storage", {})
        server_data = data.get("server", {})
        api_data = data.get("api", {})
        graph_data = data.get("graph", {})

        # Build retrieval config using helper methods
        retrieval_config = cls._build_retrieval_config(retrieval_data)
        api_config = cls._build_api_config(api_data if isinstance(api_data, dict) else {})
        graph_config = cls._build_graph_config(graph_data if isinstance(graph_data, dict) else {})

        # Build top-level config
        config_kwargs: dict[str, Any] = {
            "retrieval": retrieval_config,
            "api": api_config,
            "graph": graph_config,
        }

        # Handle storage settings
        if storage_data and storage_data.get("store_root"):
            store_root_value = storage_data.get("store_root")
            if store_root_value is not None:
                config_kwargs["store_root"] = _to_path(store_root_value, base_dir=config_dir)

        # Handle server settings
        if server_data and server_data.get("endpoint"):
            config_kwargs["endpoint"] = server_data.get("endpoint")

        # Handle embedding settings
        if embedding_data:
            if embedding_data.get("default_embed_model"):
                config_kwargs["default_embed_model"] = embedding_data.get("default_embed_model")
            if embedding_data.get("concurrency") is not None:
                config_kwargs["concurrency"] = cls._coerce_optional(embedding_data.get("concurrency"), int)
            if embedding_data.get("provider"):
                config_kwargs["embedding_provider"] = embedding_data.get("provider")
            if embedding_data.get("batch_size") is not None:
                config_kwargs["embedding_batch_size"] = cls._coerce_optional(embedding_data.get("batch_size"), int)
            if embedding_data.get("api_key_env"):
                config_kwargs["openai_api_key_env"] = embedding_data.get("api_key_env")

        # Handle top-level settings
        if data.get("per_session_spend_cap_usd") is not None:
            config_kwargs["per_session_spend_cap_usd"] = cls._coerce_optional(
                data.get("per_session_spend_cap_usd"), float
            )
        if data.get("ignore"):
            ignore_value = data.get("ignore")
            if isinstance(ignore_value, list):
                config_kwargs["ignore"] = ignore_value
        if data.get("exceptions") or data.get("ignore_exceptions"):
            config_kwargs["ignore_exceptions"] = data.get("exceptions", data.get("ignore_exceptions", []))

        # Always override retrieval config with our constructed one
        config_kwargs["retrieval"] = retrieval_config
        config_kwargs["api"] = api_config
        config_kwargs["graph"] = graph_config

        # Handle cache settings (support both nested and top-level)
        if cache_data:
            if cache_data.get("enabled") is not None:
                config_kwargs["cache_enabled"] = cls._coerce_optional(cache_data.get("enabled"), bool)
            if cache_data.get("redis_url"):
                config_kwargs["redis_url"] = cache_data.get("redis_url")
            if cache_data.get("embedding_ttl") is not None:
                config_kwargs["embedding_cache_ttl"] = cls._coerce_optional(cache_data.get("embedding_ttl"), int)
            if cache_data.get("result_ttl") is not None:
                config_kwargs["result_cache_ttl"] = cls._coerce_optional(cache_data.get("result_ttl"), int)

        # Also support top-level cache_enabled parameter (for backward compatibility)
        if "cache_enabled" in data:
            config_kwargs["cache_enabled"] = cls._coerce_optional(data.get("cache_enabled"), bool)
        if "redis_url" in data:
            redis_url_value = data.get("redis_url")
            if redis_url_value is not None:
                config_kwargs["redis_url"] = redis_url_value

        return cls(**config_kwargs)

    def resolved_store_root(self) -> Path:
        """Return the absolute path to the store root."""
        return _to_path(self.store_root)


def load_config(path: Path | None = None, repo_path: Path | None = None) -> KBConfig:
    """Load configuration strictly from file (no in-code fallbacks or env overrides).

    Resolution order (highest to lowest):
    1. Explicit path (must exist, no merge)
    2. Repo-specific config at ./.dolphin/config.toml (overrides globals)
    3. DOLPHIN_CONFIG_PATH (optional override for global config)
    4. User config at ~/.dolphin/config.toml (must exist if no repo config)

    Repo config is merged on top of the global config to keep repo overrides
    focused on per-repo settings (e.g., ignores), while inheriting global defaults.

    Raises:
        FileNotFoundError: when no configuration file is found.
        ValueError: when the loaded file is not a TOML mapping.
    """

    _DEEP_MERGE_MAX_DEPTH = 10

    def _deep_merge(base: dict[str, Any], override: dict[str, Any], _depth: int = 0) -> dict[str, Any]:
        if _depth >= _DEEP_MERGE_MAX_DEPTH:
            raise ValueError(
                f"Config nesting exceeds maximum depth ({_DEEP_MERGE_MAX_DEPTH}). "
                "Check your configuration files for excessively nested tables."
            )
        merged = dict(base)
        for key, value in override.items():
            base_value = merged.get(key)
            if isinstance(base_value, Mapping) and isinstance(value, Mapping):
                merged[key] = _deep_merge(dict(base_value), dict(value), _depth + 1)
            else:
                merged[key] = value
        return merged

    # 1) Explicit path (no merge)
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Config not found at {path}. Run 'dolphin init' to create one.")
        _log.debug("Loading config from explicit path: %s", path)
        with path.open("rb") as f:
            config_data = tomllib.load(f) or {}
        if not isinstance(config_data, Mapping):
            raise ValueError("Config must contain a mapping at the top level")
        return KBConfig.from_mapping(config_data)

    repo_config: dict[str, Any] = {}
    base_config: dict[str, Any] = {}

    # 2) Repo-specific config (optional)
    if repo_path:
        repo_config_path = repo_path / ".dolphin" / "config.toml"
        if repo_config_path.exists():
            _log.debug("Loading repo config: %s", repo_config_path)
            with repo_config_path.open("rb") as f:
                repo_config = tomllib.load(f) or {}

    # 3) Environment override for global config
    env_config_path = os.environ.get("DOLPHIN_CONFIG_PATH")
    if env_config_path:
        env_path = _to_path(env_config_path)
        if not env_path.exists():
            raise FileNotFoundError(
                f"Config not found at {env_path}. Create one with 'dolphin init' or unset DOLPHIN_CONFIG_PATH."
            )
        _log.debug("Loading config from DOLPHIN_CONFIG_PATH: %s", env_path)
        with env_path.open("rb") as f:
            base_config = tomllib.load(f) or {}
    else:
        # 4) User config fallback
        user_config = USER_CONFIG_PATH
        legacy_config = CONFIG_ROOT / "config.toml"  # Old default location prior to fix
        if user_config.exists():
            _log.debug("Loading user config: %s", user_config)
            with user_config.open("rb") as f:
                base_config = tomllib.load(f) or {}
        elif legacy_config.exists():
            _log.debug("Loading legacy config from old default location: %s", legacy_config)
            with legacy_config.open("rb") as f:
                base_config = tomllib.load(f) or {}

    if not base_config and not repo_config:
        raise ConfigNotFoundError("No configuration found. Run 'dolphin init' to create one, or provide --config path.")

    if base_config and not isinstance(base_config, Mapping):
        raise ValueError("Config must contain a mapping at the top level")
    if repo_config and not isinstance(repo_config, Mapping):
        raise ValueError("Repo config must contain a mapping at the top level")

    config_data = _deep_merge(base_config, repo_config) if base_config else repo_config
    return KBConfig.from_mapping(config_data)
