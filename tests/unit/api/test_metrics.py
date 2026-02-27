"""Unit tests for Prometheus metrics middleware."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from prometheus_client import REGISTRY

from kb.api.middleware.metrics import (
    _get_app_version,
    prometheus_middleware,
    record_db_query,
    record_embedding_call,
    record_search_query,
    record_vector_search,
    update_index_metrics,
)


def _sample_value(metric_name: str, labels: dict[str, str]) -> float | None:
    """Shorthand for REGISTRY.get_sample_value with label dict."""
    return REGISTRY.get_sample_value(metric_name, labels)


def _make_request(path: str = "/v1/search", method: str = "GET", query_string: str = "") -> MagicMock:
    """Build a minimal mock Request for the middleware under test."""
    request = MagicMock(spec=Request)
    request.method = method

    url = MagicMock()
    url.path = path
    request.url = url

    request.query_params = dict(pair.split("=", 1) for pair in query_string.split("&") if "=" in pair)

    # No matched route by default
    request.scope = {}
    return request


# ---------------------------------------------------------------------------
# Counter metric names already end with "_total", so prometheus_client does
# NOT append an additional "_total" suffix.  Histogram _count / _sum samples
# use the standard "<name>_count" / "<name>_sum" suffixes.
# ---------------------------------------------------------------------------


class TestRecordSearchQuery:
    """Test record_search_query() increments counters correctly."""

    def test_increments_search_queries_total(self):
        """Counter for total search queries is incremented."""
        labels = {"repo_name": "metrics-test-a", "search_type": "hybrid"}
        before = _sample_value("kb_search_queries_total", labels) or 0.0

        record_search_query(repo_name="metrics-test-a", search_type="hybrid", result_count=5, query_tokens=20)

        after = _sample_value("kb_search_queries_total", labels)
        assert after == before + 1

    def test_observes_result_count_histogram(self):
        """Result count histogram records the observation."""
        labels = {"repo_name": "metrics-test-b", "search_type": "semantic"}
        before = _sample_value("kb_search_result_count_count", labels) or 0.0

        record_search_query(repo_name="metrics-test-b", search_type="semantic", result_count=12, query_tokens=30)

        after = _sample_value("kb_search_result_count_count", labels)
        assert after == before + 1

        total = _sample_value("kb_search_result_count_sum", labels)
        assert total is not None
        assert total >= 12

    def test_observes_query_tokens_histogram(self):
        """Query tokens histogram records the observation."""
        labels = {"repo_name": "metrics-test-c"}
        before = _sample_value("kb_search_query_tokens_count", labels) or 0.0

        record_search_query(repo_name="metrics-test-c", search_type="keyword", result_count=0, query_tokens=42)

        after = _sample_value("kb_search_query_tokens_count", labels)
        assert after == before + 1

        total = _sample_value("kb_search_query_tokens_sum", labels)
        assert total is not None
        assert total >= 42

    def test_multiple_calls_accumulate(self):
        """Repeated calls accumulate counter and histogram values."""
        repo = "metrics-test-accum"
        labels = {"repo_name": repo, "search_type": "hybrid"}

        record_search_query(repo_name=repo, search_type="hybrid", result_count=3, query_tokens=10)
        after_first = _sample_value("kb_search_queries_total", labels)

        record_search_query(repo_name=repo, search_type="hybrid", result_count=7, query_tokens=15)
        after_second = _sample_value("kb_search_queries_total", labels)

        assert after_first is not None
        assert after_second == after_first + 1


class TestRecordVectorSearch:
    """Test record_vector_search() observes histograms."""

    def test_observes_duration_histogram(self):
        """Vector search duration histogram records the observation."""
        labels = {"repo_name": "vec-test-a"}
        before = _sample_value("kb_vector_search_duration_seconds_count", labels) or 0.0

        record_vector_search(repo_name="vec-test-a", duration_seconds=0.123)

        after = _sample_value("kb_vector_search_duration_seconds_count", labels)
        assert after == before + 1

    def test_duration_sum_accumulates(self):
        """Multiple vector search observations accumulate in the sum."""
        repo = "vec-test-sum"
        record_vector_search(repo_name=repo, duration_seconds=0.1)
        record_vector_search(repo_name=repo, duration_seconds=0.2)

        total = _sample_value("kb_vector_search_duration_seconds_sum", {"repo_name": repo})
        assert total is not None
        assert total >= 0.3


class TestRecordEmbeddingCall:
    """Test record_embedding_call() records tokens and latency."""

    def test_increments_token_counter(self):
        """Embedding token counter is incremented by the token count."""
        labels = {"repo_name": "emb-test-a"}
        before = _sample_value("kb_embedding_tokens_total", labels) or 0.0

        record_embedding_call(repo_name="emb-test-a", tokens=150, latency_seconds=0.5)

        after = _sample_value("kb_embedding_tokens_total", labels)
        assert after == before + 150

    def test_observes_latency_histogram(self):
        """Embedding API latency histogram records the observation."""
        labels = {"repo_name": "emb-test-b"}
        before = _sample_value("kb_embedding_api_latency_seconds_count", labels) or 0.0

        record_embedding_call(repo_name="emb-test-b", tokens=50, latency_seconds=1.23)

        after = _sample_value("kb_embedding_api_latency_seconds_count", labels)
        assert after == before + 1

        total = _sample_value("kb_embedding_api_latency_seconds_sum", labels)
        assert total is not None
        assert total >= 1.23

    def test_multiple_calls_accumulate_tokens(self):
        """Repeated calls accumulate in the token counter."""
        repo = "emb-test-accum"
        labels = {"repo_name": repo}
        before = _sample_value("kb_embedding_tokens_total", labels) or 0.0

        record_embedding_call(repo_name=repo, tokens=100, latency_seconds=0.1)
        record_embedding_call(repo_name=repo, tokens=200, latency_seconds=0.2)

        after = _sample_value("kb_embedding_tokens_total", labels)
        assert after == before + 300


class TestRecordDbQuery:
    """Test record_db_query() records operation metrics."""

    def test_observes_duration_histogram(self):
        """DB query duration histogram records the observation."""
        labels = {"operation": "select", "table": "chunks"}
        before = _sample_value("kb_db_query_duration_seconds_count", labels) or 0.0

        record_db_query(operation="select", table="chunks", duration_seconds=0.005)

        after = _sample_value("kb_db_query_duration_seconds_count", labels)
        assert after == before + 1

    def test_different_operations_tracked_separately(self):
        """Different operation/table combinations are tracked independently."""
        record_db_query(operation="insert", table="files", duration_seconds=0.01)
        record_db_query(operation="delete", table="files", duration_seconds=0.02)

        insert_count = _sample_value("kb_db_query_duration_seconds_count", {"operation": "insert", "table": "files"})
        delete_count = _sample_value("kb_db_query_duration_seconds_count", {"operation": "delete", "table": "files"})

        assert insert_count is not None
        assert delete_count is not None
        assert insert_count >= 1
        assert delete_count >= 1

    def test_duration_sum_reflects_observations(self):
        """Duration sum reflects the observed values."""
        table = "db_sum_test"
        record_db_query(operation="update", table=table, duration_seconds=0.05)

        total = _sample_value("kb_db_query_duration_seconds_sum", {"operation": "update", "table": table})
        assert total is not None
        assert total >= 0.05


class TestUpdateIndexMetrics:
    """Test update_index_metrics() sets gauges."""

    def test_sets_index_size_bytes(self):
        """Index size gauge is set to the provided value."""
        update_index_metrics(repo_name="idx-test-a", size_bytes=1048576, chunk_count=500)

        value = _sample_value("kb_index_size_bytes", {"repo_name": "idx-test-a"})
        assert value == 1048576

    def test_sets_indexed_chunks_total(self):
        """Indexed chunks gauge is set to the provided value."""
        update_index_metrics(repo_name="idx-test-b", size_bytes=2048, chunk_count=42)

        value = _sample_value("kb_indexed_chunks_total", {"repo_name": "idx-test-b"})
        assert value == 42

    def test_gauge_overwrites_previous_value(self):
        """Gauge set() replaces (not accumulates) the previous value."""
        update_index_metrics(repo_name="idx-test-overwrite", size_bytes=1000, chunk_count=10)
        update_index_metrics(repo_name="idx-test-overwrite", size_bytes=2000, chunk_count=20)

        size = _sample_value("kb_index_size_bytes", {"repo_name": "idx-test-overwrite"})
        chunks = _sample_value("kb_indexed_chunks_total", {"repo_name": "idx-test-overwrite"})

        assert size == 2000
        assert chunks == 20


class TestPrometheusMiddleware:
    """Test prometheus_middleware() records request metrics."""

    @pytest.mark.asyncio
    async def test_records_request_counter(self):
        """Middleware increments the HTTP requests counter."""
        request = _make_request(path="/v1/search", method="POST", query_string="repo_name=mw-test-counter")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        labels = {
            "method": "POST",
            "endpoint": "/v1/search",
            "status_code": "200",
            "repo_name": "mw-test-counter",
        }
        before = _sample_value("kb_http_requests_total", labels) or 0.0

        response = await prometheus_middleware(request, call_next)

        after = _sample_value("kb_http_requests_total", labels)
        assert after == before + 1
        assert response is mock_response

    @pytest.mark.asyncio
    async def test_records_duration_histogram(self):
        """Middleware observes HTTP request duration histogram."""
        request = _make_request(path="/v1/chunk", method="GET", query_string="repo_name=mw-test-duration")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        labels = {"method": "GET", "endpoint": "/v1/chunk", "repo_name": "mw-test-duration"}
        before = _sample_value("kb_http_request_duration_seconds_count", labels) or 0.0

        await prometheus_middleware(request, call_next)

        after = _sample_value("kb_http_request_duration_seconds_count", labels)
        assert after == before + 1

    @pytest.mark.asyncio
    async def test_records_error_status_code(self):
        """Middleware records the actual error status code from the response."""
        request = _make_request(path="/v1/search", method="GET", query_string="repo_name=mw-test-error")

        mock_response = MagicMock()
        mock_response.status_code = 404
        call_next = AsyncMock(return_value=mock_response)

        await prometheus_middleware(request, call_next)

        value = _sample_value(
            "kb_http_requests_total",
            {"method": "GET", "endpoint": "/v1/search", "status_code": "404", "repo_name": "mw-test-error"},
        )
        assert value is not None
        assert value >= 1

    @pytest.mark.asyncio
    async def test_records_500_on_exception(self):
        """Middleware records status 500 when call_next raises an exception."""
        request = _make_request(path="/v1/search", method="GET", query_string="repo_name=mw-test-exc")

        call_next = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await prometheus_middleware(request, call_next)

        value = _sample_value(
            "kb_http_requests_total",
            {"method": "GET", "endpoint": "/v1/search", "status_code": "500", "repo_name": "mw-test-exc"},
        )
        assert value is not None
        assert value >= 1

    @pytest.mark.asyncio
    async def test_extracts_repo_name_from_query_params(self):
        """Middleware extracts repo_name from query string."""
        request = _make_request(path="/v1/search", method="GET", query_string="repo_name=my-repo")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        await prometheus_middleware(request, call_next)

        value = _sample_value(
            "kb_http_requests_total",
            {"method": "GET", "endpoint": "/v1/search", "status_code": "200", "repo_name": "my-repo"},
        )
        assert value is not None
        assert value >= 1

    @pytest.mark.asyncio
    async def test_defaults_repo_name_to_unknown(self):
        """Middleware uses 'unknown' when repo_name is not in query params."""
        request = _make_request(path="/v1/health", method="GET")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        await prometheus_middleware(request, call_next)

        value = _sample_value(
            "kb_http_requests_total",
            {"method": "GET", "endpoint": "/v1/health", "status_code": "200", "repo_name": "unknown"},
        )
        assert value is not None
        assert value >= 1

    @pytest.mark.asyncio
    async def test_uses_multiple_for_repos_param(self):
        """Middleware uses 'multiple' when 'repos' query param is present."""
        request = _make_request(path="/v1/search", method="POST", query_string="repos=a,b")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        await prometheus_middleware(request, call_next)

        value = _sample_value(
            "kb_http_requests_total",
            {"method": "POST", "endpoint": "/v1/search", "status_code": "200", "repo_name": "multiple"},
        )
        assert value is not None
        assert value >= 1

    @pytest.mark.asyncio
    async def test_uses_route_template_when_available(self):
        """Middleware uses the route template path instead of the raw URL path."""
        request = _make_request(path="/v1/repos/my-repo/files", method="GET", query_string="repo_name=route-test")

        # Simulate a matched route with a template
        mock_route = MagicMock()
        mock_route.path = "/v1/repos/{repo_name}/files"
        request.scope = {"route": mock_route}

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        await prometheus_middleware(request, call_next)

        value = _sample_value(
            "kb_http_requests_total",
            {
                "method": "GET",
                "endpoint": "/v1/repos/{repo_name}/files",
                "status_code": "200",
                "repo_name": "route-test",
            },
        )
        assert value is not None
        assert value >= 1


class TestMetricsPathSkipped:
    """Test that /metrics path is skipped in middleware."""

    @pytest.mark.asyncio
    async def test_metrics_path_skips_instrumentation(self):
        """Requests to /metrics are passed through without recording metrics."""
        request = _make_request(path="/metrics", method="GET")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        # Snapshot counter state before
        before = _sample_value(
            "kb_http_requests_total",
            {"method": "GET", "endpoint": "/metrics", "status_code": "200", "repo_name": "unknown"},
        )

        response = await prometheus_middleware(request, call_next)

        # Counter should not have changed
        after = _sample_value(
            "kb_http_requests_total",
            {"method": "GET", "endpoint": "/metrics", "status_code": "200", "repo_name": "unknown"},
        )
        assert after == before
        assert response is mock_response

    @pytest.mark.asyncio
    async def test_metrics_path_still_calls_next(self):
        """The /metrics path still calls call_next to serve the response."""
        request = _make_request(path="/metrics", method="GET")

        mock_response = MagicMock()
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        await prometheus_middleware(request, call_next)

        call_next.assert_awaited_once_with(request)


class TestVersionInfo:
    """Test that the version info is set dynamically."""

    def test_get_app_version_returns_string(self):
        """_get_app_version returns a non-empty string."""
        version = _get_app_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_get_app_version_fallback_on_import_error(self):
        """_get_app_version falls back to '0.0.0' when importlib.metadata fails."""
        with patch("importlib.metadata.version", side_effect=ImportError("not installed")):
            version = _get_app_version()
            assert version == "0.0.0"

    def test_version_info_metric_contains_python_version(self):
        """The kb_api_info metric includes the python_version label."""
        import platform

        value = _sample_value(
            "kb_api_info",
            {"version": _get_app_version(), "python_version": platform.python_version()},
        )
        assert value == 1.0

    def test_version_not_hardcoded(self):
        """The version is determined dynamically, not hardcoded to a literal."""
        import inspect

        source = inspect.getsource(_get_app_version)
        # The function should use importlib.metadata, not return a hardcoded version directly
        assert "importlib" in source or "_pkg_version" in source
        # The only literal version in the source should be the fallback "0.0.0"
        version_literals = re.findall(r'"(\d+\.\d+\.\d+)"', source)
        assert version_literals == ["0.0.0"], f"Unexpected version literals in source: {version_literals}"
