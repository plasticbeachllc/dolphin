"""Server startup module that initializes the search backend."""
from __future__ import annotations
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .app import app, set_search_backend, reset_search_backend, set_stores
from .search_backend import create_search_backend
from ..config import load_config, KBConfig

def initialize_search_backend() -> None:
    """Initialize and configure the search backend based on config."""
    config: KBConfig = load_config()
    store_root = config.resolved_store_root()
    provider_type = config.embedding_provider
    provider_kwargs = {}
    if provider_type == "openai":
        api_key = os.environ.get(config.openai_api_key_env)
        if not api_key:
            print(f"⚠️  {config.openai_api_key_env} not set. Using stub provider.", file=sys.stderr)
            provider_type = "stub"
        else:
            provider_kwargs["api_key"] = api_key
            provider_kwargs["batch_size"] = config.embedding_batch_size

    print(f"🔧 Initializing search backend with '{provider_type}' provider...", file=sys.stderr)
    
    # Correctly call the stable factory function
    backend = create_search_backend(
        store_root=store_root,
        embedding_provider_type=provider_type,
        cache_enabled=config.cache_enabled,
        redis_url=config.redis_url,
        reranker_config=config.retrieval.reranking.__dict__,
        **provider_kwargs
    )
    set_search_backend(backend)
    set_stores(backend.sql_store, backend.lance_store)
    print(f"✅ Search backend ready (store: {store_root})", file=sys.stderr)

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    initialize_search_backend()
    yield
    reset_search_backend()

# Recreate the app instance to use the lifespan manager
app_with_lifespan = FastAPI(title="Dolphin Knowledge Store", version="0.1.0", lifespan=lifespan)
# Mount the original app's routes onto the new app
app_with_lifespan.router.routes.extend(app.routes)
