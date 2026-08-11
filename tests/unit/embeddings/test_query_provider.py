"""Tests for bounded fixed-contract query embedding requests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from kb.embeddings import query_provider as query_provider_module
from kb.embeddings.query_provider import OpenAIQueryEmbeddingProvider
from kb.generation import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from kb.query_embedding import (
    CredentialMissing,
    CredentialRejected,
    EmbeddingContractViolation,
    PermanentProviderFailure,
    TransientProviderFailure,
)


class _Embeddings:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Client:
    def __init__(self, outcomes: list[object]) -> None:
        self.embeddings: Any = _Embeddings(outcomes)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _StallingEmbeddings:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kwargs: object) -> object:
        self.calls += 1
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _response(
    *,
    model: str = EMBEDDING_MODEL,
    vector: object | None = None,
    index: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        model=model,
        data=[SimpleNamespace(index=index, embedding=[0.125] * EMBEDDING_DIMENSIONS if vector is None else vector)],
    )


def _status_error(
    error_type: type[openai.APIStatusError],
    status: int,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(status, request=request, headers=headers)
    return error_type(message, response=response, body={"message": message})


@pytest.mark.asyncio
async def test_missing_dolphin_credential_makes_no_client() -> None:
    created: list[str] = []
    provider = OpenAIQueryEmbeddingProvider(
        environment={"OPENAI_API_KEY": "legacy-must-not-be-read"},
        client_factory=lambda key: created.append(key),
    )

    with pytest.raises(CredentialMissing, match="DOLPHIN_OPENAI_API_KEY"):
        await provider.embed_query("where is the retry policy?")

    assert created == []


@pytest.mark.asyncio
async def test_request_pins_model_dimensions_encoding_and_timeout() -> None:
    client = _Client([_response()])
    observed_keys: list[str] = []

    def factory(key: str) -> Any:
        observed_keys.append(key)
        return client

    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": " secret-value "},
        client_factory=factory,
    )

    vector = await provider.embed_query("find the publication boundary")

    assert observed_keys == ["secret-value"]
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert client.embeddings.calls == [
        {
            "input": "find the publication boundary",
            "model": "text-embedding-3-small",
            "dimensions": 1536,
            "encoding_format": "float",
            "timeout": 5.0,
        }
    ]
    await provider.close()
    assert client.closed is True


@pytest.mark.asyncio
async def test_transient_timeout_is_retried_once() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    client = _Client([openai.APITimeoutError(request), _response()])
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
        sleep=sleep,
        random_source=lambda: 0.5,
    )

    assert len(await provider.embed_query("find the lease")) == EMBEDDING_DIMENSIONS
    assert len(client.embeddings.calls) == 2
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_retry_uses_bounded_jitter_and_safe_retry_after() -> None:
    failure = _status_error(
        openai.RateLimitError,
        429,
        "rate limited",
        headers={"retry-after": "0.75", "retry-after-ms": "500"},
    )
    client = _Client([failure, _response()])
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
        sleep=sleep,
        random_source=lambda: 1.0,
    )

    assert len(await provider.embed_query("query")) == EMBEDDING_DIMENSIONS
    assert sleeps == [0.75]


@pytest.mark.asyncio
async def test_unsafe_retry_after_is_clamped_to_interactive_budget() -> None:
    failure = _status_error(
        openai.RateLimitError,
        429,
        "rate limited",
        headers={"retry-after": "3600"},
    )
    client = _Client([failure, _response()])
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
        sleep=sleep,
        random_source=lambda: 0.5,
    )

    assert len(await provider.embed_query("query")) == EMBEDDING_DIMENSIONS
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_http_date_retry_after_is_honored_within_bounded_budget() -> None:
    observed_at = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    failure = _status_error(
        openai.RateLimitError,
        429,
        "rate limited",
        headers={"retry-after": format_datetime(observed_at + timedelta(seconds=1), usegmt=True)},
    )
    client = _Client([failure, _response()])
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
        sleep=sleep,
        random_source=lambda: 0.5,
        clock=lambda: observed_at,
    )

    assert len(await provider.embed_query("query")) == EMBEDDING_DIMENSIONS
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_outer_deadline_classifies_a_backend_that_ignores_sdk_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(query_provider_module, "_REQUEST_TIMEOUT_SECONDS", 0.01)
    client = _Client([])
    stalled = _StallingEmbeddings()
    client.embeddings = stalled

    async def no_wait(_delay: float) -> None:
        return None

    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
        sleep=no_wait,
    )

    with pytest.raises(TransientProviderFailure) as raised:
        await provider.embed_query("query")

    assert raised.value.category == "timeout"
    assert stalled.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com")), "connection"),
        (_status_error(openai.RateLimitError, 429, "sensitive rate body"), "rate_limited"),
        (_status_error(openai.APIStatusError, 503, "sensitive server body"), "server"),
    ],
)
async def test_exhausted_transient_failure_has_closed_safe_category(
    failure: Exception,
    category: str,
) -> None:
    client = _Client([failure, failure])

    async def no_wait(_delay: float) -> None:
        return None

    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret-material"},
        client_factory=lambda _key: client,
        sleep=no_wait,
    )

    with pytest.raises(TransientProviderFailure) as raised:
        await provider.embed_query("query")

    assert raised.value.category == category
    assert "sensitive" not in str(raised.value)
    assert "secret-material" not in str(raised.value)
    assert len(client.embeddings.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [openai.AuthenticationError, openai.PermissionDeniedError])
async def test_rejected_credential_is_not_retried(error_type: type[openai.APIStatusError]) -> None:
    failure = _status_error(error_type, 401, "provider payload must be redacted")
    client = _Client([failure])
    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret-material"},
        client_factory=lambda _key: client,
    )

    with pytest.raises(CredentialRejected) as raised:
        await provider.embed_query("query")

    assert "payload" not in str(raised.value)
    assert "secret-material" not in str(raised.value)
    assert len(client.embeddings.calls) == 1


@pytest.mark.asyncio
async def test_permanent_request_failure_is_not_retried() -> None:
    failure = _status_error(openai.BadRequestError, 400, "raw provider request body")
    client = _Client([failure])
    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
    )

    with pytest.raises(PermanentProviderFailure) as raised:
        await provider.embed_query("query")

    assert raised.value.category == "request_rejected"
    assert "raw provider" not in str(raised.value)
    assert len(client.embeddings.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _response(model="text-embedding-3-large"),
        _response(vector=[0.1] * (EMBEDDING_DIMENSIONS - 1)),
        _response(vector=[0.0] * EMBEDDING_DIMENSIONS),
        _response(vector=[float("nan")] * EMBEDDING_DIMENSIONS),
        _response(index=1),
        SimpleNamespace(model=EMBEDDING_MODEL, data=[]),
    ],
)
async def test_incompatible_provider_response_fails_closed(response: object) -> None:
    client = _Client([response])
    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
    )

    with pytest.raises(EmbeddingContractViolation):
        await provider.embed_query("query")

    assert len(client.embeddings.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "x" * 2_001, "\ud800"])
async def test_invalid_query_never_reaches_provider(query: str) -> None:
    client = _Client([_response()])
    provider = OpenAIQueryEmbeddingProvider(
        environment={"DOLPHIN_OPENAI_API_KEY": "secret"},
        client_factory=lambda _key: client,
    )

    with pytest.raises(EmbeddingContractViolation):
        await provider.embed_query(query)

    assert client.embeddings.calls == []
