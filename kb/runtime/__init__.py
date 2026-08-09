"""Process-lifetime runtime primitives for Dolphin 0.3.0."""

from kb.runtime.storage import StorageLayout, StorageLayoutError, macos_storage_layout

__all__ = ["StorageLayout", "StorageLayoutError", "macos_storage_layout"]
