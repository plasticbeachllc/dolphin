"""Server startup module that initializes the search backend."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import KBConfig, load_config
from ..terminal import print_hint, print_status

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


def _load_timeout_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logging.getLogger(__name__).warning("Invalid %s=%r; using default %.1fs", name, raw, default)
        return default
    if value <= 0:
        logging.getLogger(__name__).warning("Non-positive %s=%r; using default %.1fs", name, raw, default)
        return default
    return value


_WATCHER_SHUTDOWN_GRACE_SECONDS = _load_timeout_from_env("DOLPHIN_WATCH_SHUTDOWN_TIMEOUT", 15.0)
_WATCHER_CANCEL_GRACE_SECONDS = _load_timeout_from_env("DOLPHIN_WATCH_CANCEL_TIMEOUT", 5.0)


def initialize_search_backend() -> None:
    """Initialize and configure the search backend and ingestion pipeline based on config."""
    config: KBConfig = load_config()
    store_root = config.resolved_store_root()
    provider_type = config.embedding_provider
    provider_kwargs = {}
    if provider_type == "openai":
        api_key = os.environ.get(config.openai_api_key_env)
        if not api_key:
            print_status(
                f"{config.openai_api_key_env} not set. Falling back to stub embedding provider.",
                level="warn",
                stderr=True,
            )
            provider_type = "stub"
        else:
            print_status(
                f"Using OpenAI embedding provider from {config.openai_api_key_env}.",
                level="success",
                stderr=True,
            )
            provider_kwargs["api_key"] = api_key
            provider_kwargs["batch_size"] = config.embedding_batch_size

    print_status(
        "Initializing search backend.",
        level="step",
        context={"provider": provider_type},
        stderr=True,
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

    # Crash recovery: abort any sessions left running from prior processes
    try:
        aborted = backend.sql_store.abort_stale_sessions(
            reason="Aborted on startup: previous indexing session did not complete cleanly"
        )
        if aborted:
            print_status(
                "Aborted stale indexing sessions from a previous process.",
                level="warn",
                context={"sessions": aborted},
                stderr=True,
            )
    except Exception as e:
        print_status(
            "Failed to abort stale indexing sessions.",
            level="warn",
            context={"error": str(e)},
            stderr=True,
        )

    print_status(
        "Search backend ready.",
        level="success",
        context={"store": store_root},
        stderr=True,
    )

    # Initialize ingestion pipeline for full reindex operations
    print_status("Initializing ingestion pipeline.", level="step", stderr=True)
    from ..ingest.pipeline import IngestionPipeline
    from ..store.graph_store import GraphStore

    # Create pipeline with same stores as backend
    pipeline = IngestionPipeline(
        config=config,
        lancedb=backend.lance_store,
        metadata=backend.sql_store,
        graph_store=GraphStore(backend.sql_store.db_path),
        cache=backend.cache,
    )
    set_pipeline(pipeline)
    print_status("Ingestion pipeline ready.", level="success", stderr=True)

    # Warn about embedding model mismatches between config and registered repos.
    # The watcher startup sync will auto-trigger full reindex for mismatched repos,
    # but the user should see an explicit heads-up.
    config_model = config.default_embed_model
    repos = backend.sql_store.list_all_repos()
    for repo in repos:
        repo_model = repo.get("default_embed_model", "large")
        if repo_model != config_model:
            print_status(
                f"Embedding model mismatch for '{repo['name']}': "
                f"indexed with '{repo_model}', config says '{config_model}'. "
                f"A full re-index will run automatically on startup sync.",
                level="warn",
                stderr=True,
            )


def reload_search_backend() -> None:
    """Reload the search backend and stores to pick up index changes."""
    print_status("Reloading search backend.", level="step", stderr=True)
    try:
        # Initialize first; only reset the old backend on success so that a
        # failed re-initialization never leaves the server with an empty backend.
        initialize_search_backend()
        print_status("Search backend reloaded.", level="success", stderr=True)
    except Exception as e:
        print_status(
            "Failed to reload search backend.",
            level="error",
            context={"error": str(e)},
            stderr=True,
        )
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
        print_status("Initializing dolphin server runtime.", level="step", stderr=True)
        try:
            initialize_search_backend()
        except FileNotFoundError:
            print_status(
                "No KB configuration found.",
                level="warn",
                stderr=True,
            )
            print_hint("Run `dolphin init` before starting the server.", stderr=True)
        except Exception as exc:
            logging.getLogger(__name__).error("Search backend initialization failed.", exc_info=True)
            print_status(
                "Backend initialization failed; server cannot start.",
                level="error",
                context={"error": str(exc)},
                stderr=True,
            )
            raise

    # Start watchers if configured
    watchers = []
    watch_tasks = []
    watch_repos = os.environ.get("DOLPHIN_WATCH_REPOS")
    if watch_repos:
        repo_names = [r.strip() for r in watch_repos.split(",") if r.strip()]
        if repo_names:
            print_status(
                "Starting repository watchers.",
                level="step",
                context={"repos": ",".join(repo_names)},
                stderr=True,
            )
            try:
                from ..ingest.watcher import RepoWatcher

                pipeline = get_pipeline()
                if pipeline:
                    config = load_config()
                    for repo_name in repo_names:
                        watcher = RepoWatcher(repo_name, config, pipeline)
                        watchers.append(watcher)
                        task = asyncio.create_task(watcher.watch())
                        watch_tasks.append(task)
                else:
                    print_status(
                        "Pipeline not initialized; skipping watcher startup.",
                        level="warn",
                        stderr=True,
                    )
            except ImportError as e:
                print_status(
                    "Failed to import RepoWatcher; watcher startup skipped.",
                    level="warn",
                    context={"error": str(e)},
                    stderr=True,
                )
            except Exception as e:
                print_status(
                    "Failed to start watchers.",
                    level="warn",
                    context={"error": str(e)},
                    stderr=True,
                )

    yield  # Application is running

    # Shutdown: Clean up resources
    print_status("Shutting down dolphin server runtime.", level="step", stderr=True)

    # Signal the ingestion pipeline to stop processing between files.
    # This allows any in-progress index/process_files call running in a
    # watcher thread (or background task) to exit cooperatively rather than
    # continuing to process the entire file list after Ctrl-C.
    pipeline = get_pipeline()
    if pipeline is not None:
        try:
            pipeline.request_cancel()
        except Exception as e:
            print_status(
                "Failed to request pipeline cancellation.", level="warn", context={"error": str(e)}, stderr=True
            )

    # Cancel watcher tasks
    if watch_tasks:
        print_status(
            "Stopping repository watchers.",
            level="step",
            context={"watchers": len(watch_tasks)},
            stderr=True,
        )
        for watcher in watchers:
            try:
                watcher.request_stop()
            except Exception as e:
                print_status(
                    "Watcher stop request failed.",
                    level="warn",
                    context={"error": str(e)},
                    stderr=True,
                )

        done, pending = await asyncio.wait(watch_tasks, timeout=_WATCHER_SHUTDOWN_GRACE_SECONDS)

        if pending:
            for task in pending:
                task.cancel()
            cancelled_done, cancelled_pending = await asyncio.wait(pending, timeout=_WATCHER_CANCEL_GRACE_SECONDS)
            done = done.union(cancelled_done)
            if cancelled_pending:
                print_status(
                    "Watchers did not stop gracefully before timeout.",
                    level="warn",
                    context={"pending": len(cancelled_pending)},
                    stderr=True,
                )

        for task in done:
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                continue
            if exc:
                print_status(
                    "Watcher exited with error during shutdown.",
                    level="warn",
                    context={"error": str(exc)},
                    stderr=True,
                )

    # Close embedding provider if it has async client
    if _embedding_provider and hasattr(_embedding_provider, "close"):
        try:
            await _embedding_provider.close()
            print_status("Closed embedding provider.", level="success", stderr=True)
        except Exception as e:
            print_status(
                "Failed to close embedding provider cleanly.",
                level="warn",
                context={"error": str(e)},
                stderr=True,
            )

    reset_search_backend()
    print_status("Server shutdown complete.", level="success", stderr=True)


# Assign lifespan to the app
app.router.lifespan_context = lifespan_handler

# Export the app for uvicorn
app_with_lifespan = app


def main():
    """Entry point for kb-api command."""
    import uvicorn

    dev_mode = os.environ.get("DOLPHIN_DEV_MODE", "").lower() in ("1", "true", "yes")
    uvicorn.run("kb.api.server:app_with_lifespan", host="0.0.0.0", port=8000, reload=dev_mode)


if __name__ == "__main__":
    main()
