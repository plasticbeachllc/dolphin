"""
Prometheus metrics middleware for FastAPI.
Instruments all endpoints with request/response metrics.
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY
)
from fastapi import Request, Response
from fastapi.responses import Response as FastAPIResponse
from typing import Callable
import time

# ============================================================================
# Metrics Definitions
# ============================================================================

# Request metrics
http_requests_total = Counter(
    'kb_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code', 'repo_name']
)

http_request_duration_seconds = Histogram(
    'kb_http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint', 'repo_name'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Search-specific metrics
search_queries_total = Counter(
    'kb_search_queries_total',
    'Total search queries',
    ['repo_name', 'search_type']  # search_type: semantic, hybrid, keyword
)

search_result_count = Histogram(
    'kb_search_result_count',
    'Number of results returned per search',
    ['repo_name', 'search_type'],
    buckets=[0, 1, 5, 10, 20, 50, 100]
)

search_query_tokens = Histogram(
    'kb_search_query_tokens',
    'Query token count',
    ['repo_name'],
    buckets=[10, 25, 50, 100, 200, 500]
)

# Embedding metrics
embedding_tokens_total = Counter(
    'kb_embedding_tokens_total',
    'Total tokens embedded',
    ['repo_name']
)

embedding_api_latency_seconds = Histogram(
    'kb_embedding_api_latency_seconds',
    'OpenAI embedding API latency',
    ['repo_name'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

embedding_cost_usd = Counter(
    'kb_embedding_cost_usd',
    'Total embedding costs in USD',
    ['repo_name', 'model']
)

# Database metrics
db_query_duration_seconds = Histogram(
    'kb_db_query_duration_seconds',
    'Database query duration',
    ['operation', 'table'],  # operation: select, insert, update, delete
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

vector_search_duration_seconds = Histogram(
    'kb_vector_search_duration_seconds',
    'LanceDB vector search duration',
    ['repo_name'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

# Index metrics
index_size_bytes = Gauge(
    'kb_index_size_bytes',
    'Total index size in bytes',
    ['repo_name']
)

indexed_chunks_total = Gauge(
    'kb_indexed_chunks_total',
    'Total number of indexed chunks',
    ['repo_name']
)

# System info
kb_info = Info(
    'kb_api',
    'Knowledge Bank API information'
)
kb_info.info({
    'version': '1.0.0',
    'python_version': '3.12'
})

# ============================================================================
# Middleware
# ============================================================================

async def prometheus_middleware(request: Request, call_next: Callable):
    """
    Middleware to record HTTP request metrics.
    Adds minimal overhead: ~1-2ms per request.
    """
    # Skip metrics endpoint to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)

    # Extract metadata
    method = request.method
    # Default to the raw path; we'll replace with the route template when available
    path = request.url.path

    # Extract repo_name from query params or path
    repo_name = request.query_params.get('repo_name', 'unknown')
    if 'repos' in request.query_params:
        repo_name = 'multiple'

    # Start timer
    start_time = time.perf_counter()

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as e:
        status_code = 500
        raise
    finally:
        # Determine the best identifier for the route. Using the route template keeps
        # cardinality low for Prometheus metrics even when requests include dynamic
        # segments (e.g., repo names, file paths).
        route = request.scope.get("route")
        if route is not None:
            path = getattr(route, "path", None) or getattr(route, "path_format", path)

        # Record metrics
        duration = time.perf_counter() - start_time

        http_requests_total.labels(
            method=method,
            endpoint=path,
            status_code=status_code,
            repo_name=repo_name
        ).inc()

        http_request_duration_seconds.labels(
            method=method,
            endpoint=path,
            repo_name=repo_name
        ).observe(duration)


# ============================================================================
# Metrics Endpoint
# ============================================================================

async def metrics_endpoint(request: Request) -> FastAPIResponse:
    """
    Expose Prometheus metrics at /metrics endpoint.
    """
    return FastAPIResponse(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )


# ============================================================================
# Helper Functions for Instrumenting Code
# ============================================================================

def record_search_query(repo_name: str, search_type: str, result_count: int, query_tokens: int):
    """Record metrics for a search query."""
    search_queries_total.labels(
        repo_name=repo_name,
        search_type=search_type
    ).inc()

    search_result_count.labels(
        repo_name=repo_name,
        search_type=search_type
    ).observe(result_count)

    search_query_tokens.labels(
        repo_name=repo_name
    ).observe(query_tokens)


def record_vector_search(repo_name: str, duration_seconds: float):
    """Record metrics for vector search operation."""
    vector_search_duration_seconds.labels(
        repo_name=repo_name
    ).observe(duration_seconds)


def record_embedding_call(repo_name: str, model: str, tokens: int, latency_seconds: float):
    """Record metrics for embedding API call."""
    embedding_tokens_total.labels(
        repo_name=repo_name
    ).inc(tokens)

    embedding_api_latency_seconds.labels(
        repo_name=repo_name
    ).observe(latency_seconds)

    # Calculate cost (text-embedding-3-small: $0.02 per 1M tokens)
    cost = (tokens / 1_000_000) * 0.02
    embedding_cost_usd.labels(
        repo_name=repo_name,
        model=model
    ).inc(cost)


def record_db_query(operation: str, table: str, duration_seconds: float):
    """Record metrics for database query."""
    db_query_duration_seconds.labels(
        operation=operation,
        table=table
    ).observe(duration_seconds)


def update_index_metrics(repo_name: str, size_bytes: int, chunk_count: int):
    """Update index size and chunk count metrics."""
    index_size_bytes.labels(repo_name=repo_name).set(size_bytes)
    indexed_chunks_total.labels(repo_name=repo_name).set(chunk_count)
