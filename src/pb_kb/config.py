from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .ignores import DEFAULT_IGNORE_PATTERNS

CONFIG_ROOT = Path.home() / ".dolphin" / "knowledge_store"
DEFAULT_CONFIG_PATH = CONFIG_ROOT / "config.toml"


def _to_path(value: Any) -> Path:
    if isinstance(value, Path):
        return value.expanduser().resolve()
    return Path(str(value)).expanduser().resolve()


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

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KBConfig":
        """Create a configuration object from a mapping."""
        ignore_values = data.get("ignore") or DEFAULT_IGNORE_PATTERNS
        retrieval = data.get("retrieval") or {}
        embedding = data.get("embedding") or {}
        return cls(
            store_root=_to_path(data.get("store_root", CONFIG_ROOT)),
            endpoint=str(data.get("endpoint", "127.0.0.1:7777")),
            default_embed_model=str(data.get("default_embed_model", "small")),
            concurrency=int(data.get("concurrency", 3)),
            per_session_spend_cap_usd=float(
                data.get("per_session_spend_cap_usd", 10.0)
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
        )

    def resolved_store_root(self) -> Path:
        """Return the absolute path to the store root."""
        return _to_path(self.store_root)


def load_config(path: Path | None = None) -> KBConfig:
    """Load configuration values from disk or fall back to defaults."""
    config_path = path or DEFAULT_CONFIG_PATH
    if config_path.exists():
        with config_path.open("rb") as handle:
            data = tomllib.load(handle) or {}
        if not isinstance(data, Mapping):
            raise ValueError(f"Config file {config_path} must contain a mapping.")
        return KBConfig.from_mapping(data)
    return KBConfig()
