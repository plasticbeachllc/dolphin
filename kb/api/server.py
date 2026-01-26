"""Server startup module that initializes the search backend."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import KBConfig, load_config

# Note on Environment Variable Management:
# This server expects environment variables (e.g., OPENAI_API_KEY, DOLPHIN_CONFIG_PATH)
# to be provided by the host environment (shell, Docker, etc.).
# Auto-loading via .env files is intentionally excluded to maintain
# consistency across different deployment environments.
from .app import app, get_pipeline, reset_search_backend, set_pipeline, set_search_backend, set_stores
from .middleware.metrics import metrics_endpoint, prometheus_middleware
from .search_backend import create_search_backend

# Configure logging to output to stderr at INFO level
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] [%(name)s] %(message)s",
    stream=sys.stderr,
)


def initialize_search_backend() -> None:
    """Initialize and configure the search backend and ingestion pipeline based on config."""
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
        default_embed_model=config.default_embed_model,
        cache_enabled=config.cache_enabled,
        redis_url=config.redis_url,
        reranker_config=config.retrieval.reranking.__dict__,
        **provider_kwargs,
    )
    set_search_backend(backend)
    set_stores(backend.sql_store, backend.lance_store)

    # Store embedding provider reference for cleanup
    global _embedding_provider
    _embedding_provider = backend.embedding_provider

    print(f"✅ Search backend ready (store: {store_root})", file=sys.stderr)

    # Initialize ingestion pipeline for full reindex operations
    print("🔧 Initializing ingestion pipeline...", file=sys.stderr)
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
    print("✅ Ingestion pipeline ready", file=sys.stderr)


def reload_search_backend() -> None:
    """Reload the search backend and stores to pick up index changes."""
    print("🔄 Reloading search backend...", file=sys.stderr)
    try:
        # Reset existing backend first to force fresh connections
        reset_search_backend()
        initialize_search_backend()
        print("✅ Search backend reloaded successfully", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to reload search backend: {e}", file=sys.stderr)
        raise


# Add Prometheus metrics middleware to the app
app.middleware("http")(prometheus_middleware)

# Add metrics endpoint to the app
app.get("/metrics")(metrics_endpoint)


# Store embedding provider reference for cleanup
_embedding_provider = None


# Define lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan_handler(app_instance: FastAPI):
    """Manage application lifespan (startup and shutdown)."""
    global _embedding_provider

    # Startup: Initialize backend/pipeline if not already initialized.
    # Avoid module import-time side effects (important for test collection and xdist).
    if get_pipeline() is None:
        print("🚀 Initializing KB server...", file=sys.stderr)
        try:
            initialize_search_backend()
        except FileNotFoundError:
            print(
                "⚠️  No KB configuration found. Create a config, then call initialize_search_backend().",
                file=sys.stderr,
            )

    # Start watchers if configured
    watch_tasks = []
    watch_repos = os.environ.get("DOLPHIN_WATCH_REPOS")
    if watch_repos:
        repo_names = [r.strip() for r in watch_repos.split(",") if r.strip()]
        if repo_names:
            print(f"👀 Starting watchers for repositories: {', '.join(repo_names)}", file=sys.stderr)
            try:
                from ..ingest.watcher import RepoWatcher

                pipeline = get_pipeline()
                if pipeline:
                    config = load_config()
                    for repo_name in repo_names:
                        watcher = RepoWatcher(repo_name, config, pipeline)
                        task = asyncio.create_task(watcher.watch())
                        watch_tasks.append(task)
                else:
                    print("⚠️  Pipeline not initialized, cannot start watchers", file=sys.stderr)
            except ImportError as e:
                print(f"⚠️  Failed to import RepoWatcher: {e}", file=sys.stderr)
            except Exception as e:
                print(f"⚠️  Failed to start watchers: {e}", file=sys.stderr)

    yield  # Application is running

    # Shutdown: Clean up resources
    print("🛑 Shutting down KB server...", file=sys.stderr)

    # Cancel watcher tasks
    if watch_tasks:
        print(f"🛑 Stopping {len(watch_tasks)} watchers...", file=sys.stderr)
        for task in watch_tasks:
            task.cancel()
        try:
            await asyncio.wait(watch_tasks, timeout=5.0)
        except TimeoutError:
            print("⚠️  Watchers did not stop gracefully", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Error stopping watchers: {e}", file=sys.stderr)

    # Close embedding provider if it has async client
    if _embedding_provider and hasattr(_embedding_provider, "close"):
        try:
            await _embedding_provider.close()
            print("✅ Closed embedding provider", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Failed to close embedding provider: {e}", file=sys.stderr)

    reset_search_backend()
    print("✅ KB server shutdown complete", file=sys.stderr)


# Assign lifespan to the app
app.router.lifespan_context = lifespan_handler

# Export the app for uvicorn
app_with_lifespan = app


def main():
    """Entry point for kb-api command."""
    import uvicorn

    uvicorn.run("kb.api.server:app_with_lifespan", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
