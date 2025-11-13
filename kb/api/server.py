"""Server startup module that initializes the search backend."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import KBConfig, load_config
from .app import app, reset_search_backend, set_pipeline, set_search_backend, set_stores
from .middleware.metrics import metrics_endpoint, prometheus_middleware
from .search_backend import create_search_backend

# Configure logging to output to stderr at INFO level
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] [%(name)s] %(message)s",
    stream=sys.stderr,
)


# Load environment variables from .env file if it exists
def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent.parent.parent / ".env"
    if env_file.exists():
        print(f"📄 Loading environment variables from {env_file}", file=sys.stderr)
        try:
            # Simple .env parser
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip().strip("\"'")
        except Exception as e:
            print(f"⚠️  Failed to load .env file: {e}", file=sys.stderr)
    else:
        print(f"ℹ️  No .env file found at {env_file}", file=sys.stderr)


def initialize_search_backend() -> None:
    """Initialize and configure the search backend and ingestion pipeline based on config."""
    # Load environment variables from .env file
    load_env_file()

    config: KBConfig = load_config()
    store_root = config.resolved_store_root()
    provider_type = config.embedding_provider
    provider_kwargs = {}
    if provider_type == "openai":
        api_key = os.environ.get(config.openai_api_key_env)
        if not api_key:
            print(
                f"⚠️  {config.openai_api_key_env} not set. Using stub provider.",
                file=sys.stderr,
            )
            provider_type = "stub"
        else:
            print(
                f"✅ Found {config.openai_api_key_env}, using OpenAI provider",
                file=sys.stderr,
            )
            provider_kwargs["api_key"] = api_key
            provider_kwargs["batch_size"] = config.embedding_batch_size

    print(
        f"🔧 Initializing search backend with '{provider_type}' provider...",
        file=sys.stderr,
    )

    # Correctly call the stable factory function
    backend = create_search_backend(
        store_root=store_root,
        embedding_provider_type=provider_type,
        cache_enabled=config.cache_enabled,
        redis_url=config.redis_url,
        reranker_config=config.retrieval.reranking.__dict__,
        **provider_kwargs,
    )
    set_search_backend(backend)
    set_stores(backend.sql_store, backend.lance_store)
    print(f"✅ Search backend ready (store: {store_root})", file=sys.stderr)

    # Initialize ingestion pipeline for full reindex operations
    print(f"🔧 Initializing ingestion pipeline...", file=sys.stderr)
    from ..ingest.pipeline import IngestionPipeline
    from ..store.graph_store import GraphStore

    # Create pipeline with same stores as backend
    pipeline = IngestionPipeline(
        config=config,
        lancedb=backend.lance_store,
        metadata=backend.sql_store,
        graph_store=GraphStore(backend.sql_store.db_path),
    )
    set_pipeline(pipeline)
    print(f"✅ Ingestion pipeline ready", file=sys.stderr)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    initialize_search_backend()
    yield
    reset_search_backend()


# Recreate the app instance to use the lifespan manager
app_with_lifespan = FastAPI(
    title="Dolphin Knowledge Store", version="0.1.0", lifespan=lifespan
)

# Add CORS middleware to allow requests from VSCode webviews
app_with_lifespan.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (webview origins are dynamic)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the original app's routes onto the new app
app_with_lifespan.router.routes.extend(app.routes)

# Add Prometheus metrics middleware
app_with_lifespan.middleware("http")(prometheus_middleware)

# Add metrics endpoint
app_with_lifespan.get("/metrics")(metrics_endpoint)


# Add health check endpoint
@app_with_lifespan.get("/health")
async def health_check():
    """Enhanced health check with component status."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {"api": "healthy"},
    }


def main():
    """Entry point for kb-api command."""
    import uvicorn

    uvicorn.run(
        "kb.api.server:app_with_lifespan", host="0.0.0.0", port=8000, reload=True
    )


if __name__ == "__main__":
    main()
