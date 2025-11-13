"""Compatibility shim exposing the legacy KBPipeline interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import KBConfig
from .ingest.pipeline import IngestionPipeline
from .store import LanceDBStore, SQLiteMetadataStore


class KBPipeline(IngestionPipeline):
    """Backward compatible wrapper around :class:`IngestionPipeline`.

    Historical callers constructed ``KBPipeline`` directly. The modern codebase
    renamed the implementation to :class:`IngestionPipeline`. This subclass keeps
    the old import path working while defaulting the :class:`KBConfig` store
    root to the LanceDB directory that tests build in temporary locations.
    """

    def __init__(
        self,
        metadata_store: SQLiteMetadataStore,
        lancedb_store: LanceDBStore,
        *,
        config: KBConfig | None = None,
        **kwargs: Any,
    ) -> None:
        if config is None:
            store_root = getattr(lancedb_store, "root", None)
            config = KBConfig(store_root=Path(store_root)) if store_root else KBConfig()
        super().__init__(
            config=config, lancedb=lancedb_store, metadata=metadata_store, **kwargs
        )


__all__ = ["KBPipeline"]
