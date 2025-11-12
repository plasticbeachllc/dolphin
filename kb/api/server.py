"""Server startup module that initializes the search backend."""
from __future__ import annotations
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .app import app, set_search_backend, reset_search_backend, set_stores, set_pipeline
from .search_backend import create_search_backend
from ..config import load_config, KBConfig
from .middleware.metrics import prometheus_middleware, metrics_endpoint

# Configure logging to output to stderr at INFO level
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(name)s] %(message)s',
    stream=sys.stderr
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
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"\'')
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
            print(f"⚠️  {config.openai_api_key_env} not set. Using stub provider.", file=sys.stderr)
            provider_type = "stub"
        else:
            print(f"✅ Found {config.openai_api_key_env}, using OpenAI provider", file=sys.stderr)
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

    # Store embedding provider reference for cleanup
    global _embedding_provider
    _embedding_provider = backend.embedding_provider

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
        graph_store=GraphStore(backend.sql_store.db_path)
    )
    set_pipeline(pipeline)
    print(f"✅ Ingestion pipeline ready", file=sys.stderr)

# Initialize search backend when module loads (before uvicorn starts)
print(f"🚀 Initializing KB server...", file=sys.stderr)
initialize_search_backend()

# Add Prometheus metrics middleware to the app
app.middleware("http")(prometheus_middleware)

# Add metrics endpoint to the app
app.get("/metrics")(metrics_endpoint)

# Add health check endpoint to the app
@app.get("/health")
async def health_check():
    """Enhanced health check with component status."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "api": "healthy"
        }
    }

# Store embedding provider reference for cleanup
_embedding_provider = None

# Define lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan_handler(app_instance: FastAPI):
    """Manage application lifespan (startup and shutdown)."""
    global _embedding_provider
    
    # Startup is handled by module-level initialization (line 95-96)
    # This keeps existing behavior where backend is ready before uvicorn starts
    yield  # Application is running
    
    # Shutdown: Clean up resources
    print(f"🛑 Shutting down KB server...", file=sys.stderr)
    
    # Close embedding provider if it has async client
    if _embedding_provider and hasattr(_embedding_provider, 'close'):
        try:
            await _embedding_provider.close()
            print(f"✅ Closed embedding provider", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Failed to close embedding provider: {e}", file=sys.stderr)
    
    reset_search_backend()
    print(f"✅ KB server shutdown complete", file=sys.stderr)

# Assign lifespan to the app
app.router.lifespan_context = lifespan_handler

# Export the app for uvicorn
app_with_lifespan = app

def main():
    """Entry point for kb-api command."""
    import uvicorn
    uvicorn.run(
        "kb.api.server:app_with_lifespan",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

if __name__ == "__main__":
    main()
