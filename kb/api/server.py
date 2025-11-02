"""Server startup module that initializes the search backend."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from .app import app, set_search_backend, reset_search_backend, set_stores
from .search_backend import create_search_backend
from ..config import load_config


def initialize_search_backend() -> None:
    """Initialize and configure the search backend based on config."""
    # Load configuration
    config = load_config()

    store_root = config.resolved_store_root()

    # Determine embedding provider type from config
    provider_type = config.embedding_provider

    # Prepare kwargs for provider
    provider_kwargs = {}
    if provider_type == "openai":
        # Get API key from environment
        api_key = os.environ.get(config.openai_api_key_env)
        if not api_key:
            print(f"⚠️  {config.openai_api_key_env} not set. Using stub provider.", file=sys.stderr)
            print(f"   For real embeddings: export {config.openai_api_key_env}=sk-...", file=sys.stderr)
            # Fall back to stub provider
            provider_type = "stub"
        else:
            provider_kwargs["api_key"] = api_key
            provider_kwargs["batch_size"] = config.embedding_batch_size

    # Create backend
    print(f"🔧 Initializing search backend with '{provider_type}' embedding provider...", file=sys.stderr)
    backend = create_search_backend(
        store_root,
        embedding_provider_type=provider_type,
        **provider_kwargs
    )

    # Set for API
    set_search_backend(backend)

    # Also set the stores for other endpoints
    set_stores(backend.sql_store, backend.lance_store)

    print(f"✅ Search backend ready (store: {store_root})", file=sys.stderr)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    initialize_search_backend()
    yield
    # Shutdown
    reset_search_backend()


# Create a new FastAPI app with lifespan
app_with_lifespan = FastAPI(
    title="Unified Knowledge Store",
    version="0.1.0",
    lifespan=lifespan
)

# Copy routes from original app
for route in app.routes:
    app_with_lifespan.routes.append(route)


def main() -> None:
    """Start the API server with search backend initialized."""
    import uvicorn

    print("\n" + "="*60, file=sys.stderr)
    print("  Knowledge Base Search API", file=sys.stderr)
    print("="*60, file=sys.stderr)

    uvicorn.run(
        "kb.api.server:app_with_lifespan",
        host="127.0.0.1",
        port=7777,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
