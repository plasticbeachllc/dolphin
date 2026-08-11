"""Bounded OpenAI adapter for the fixed query-embedding contract."""

from __future__ import annotations

import asyncio
import math
import os
import random
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol, cast

import openai
from openai import AsyncOpenAI

from kb.artifacts import ArtifactInputInvalid, identify_embedding_input
from kb.generation import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from kb.generation_vector import canonicalize_embedding_vector
from kb.query_embedding import (
    MAX_QUERY_CHARACTERS,
    CredentialMissing,
    CredentialRejected,
    EmbeddingContractViolation,
    PermanentProviderFailure,
    QueryEmbeddingError,
    TransientProviderFailure,
)

DOLPHIN_OPENAI_API_KEY = "DOLPHIN_OPENAI_API_KEY"
_REQUEST_TIMEOUT_SECONDS = 5.0
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 0.25


class _EmbeddingResource(Protocol):
    async def create(
        self,
        *,
        input: str,
        model: str,
        dimensions: int,
        encoding_format: str,
        timeout: float,
    ) -> Any: ...


class _AsyncOpenAIClient(Protocol):
    embeddings: _EmbeddingResource

    async def close(self) -> None: ...


ClientFactory = Callable[[str], _AsyncOpenAIClient]
AsyncSleep = Callable[[float], Awaitable[None]]
RandomSource = Callable[[], float]
Clock = Callable[[], datetime]

_RETRY_JITTER_FRACTION = 0.25
_MAX_RETRY_DELAY_SECONDS = 1.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class OpenAIQueryEmbeddingProvider:
    """Make one redacted, fixed-model request under a short retry budget."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        client_factory: ClientFactory | None = None,
        sleep: AsyncSleep = asyncio.sleep,
        random_source: RandomSource = random.random,
        clock: Clock = _utc_now,
    ) -> None:
        self._environment = os.environ if environment is None else environment
        self._client_factory = client_factory or _default_client
        self._sleep = sleep
        self._random_source = random_source
        self._clock = clock
        self._client: _AsyncOpenAIClient | None = None
        self._client_condition = asyncio.Condition()
        self._active_requests = 0
        self._closing = False

    async def embed_query(self, query: str) -> tuple[float, ...]:
        """Return one canonical vector or a closed, safe failure category."""
        _require_query(query)
        api_key = self._environment.get(DOLPHIN_OPENAI_API_KEY, "").strip()
        if not api_key:
            raise CredentialMissing("Dolphin requires DOLPHIN_OPENAI_API_KEY in the MCP server environment")
        client = await self._acquire_client(api_key)
        try:
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    async with asyncio.timeout(_REQUEST_TIMEOUT_SECONDS):
                        response = await client.embeddings.create(
                            input=query,
                            model=EMBEDDING_MODEL,
                            dimensions=EMBEDDING_DIMENSIONS,
                            encoding_format="float",
                            timeout=_REQUEST_TIMEOUT_SECONDS,
                        )
                    return _vector_from_response(response)
                except QueryEmbeddingError:
                    raise
                except Exception as exc:
                    failure = _classified_failure(exc)
                    if isinstance(failure, TransientProviderFailure) and attempt + 1 < _MAX_ATTEMPTS:
                        await self._sleep(_safe_retry_delay(exc, self._random_source, self._clock))
                        continue
                    raise failure from None
            raise PermanentProviderFailure("provider_error")
        finally:
            await self._release_client()

    async def close(self) -> None:
        """Drain active request leases, then release the SDK client."""
        async with self._client_condition:
            while self._closing:
                await self._client_condition.wait()
            self._closing = True
            try:
                await self._client_condition.wait_for(lambda: self._active_requests == 0)
            except BaseException:
                self._closing = False
                self._client_condition.notify_all()
                raise
            client, self._client = self._client, None
        try:
            if client is not None:
                await client.close()
        except Exception:
            raise PermanentProviderFailure("provider_error") from None
        finally:
            async with self._client_condition:
                self._closing = False
                self._client_condition.notify_all()

    async def _acquire_client(self, api_key: str) -> _AsyncOpenAIClient:
        async with self._client_condition:
            while self._closing:
                await self._client_condition.wait()
            client = self._client
            if client is None:
                try:
                    client = self._client_factory(api_key)
                except Exception as exc:
                    _raise_classified(exc)
                assert client is not None
                self._client = client
            self._active_requests += 1
            return client

    async def _release_client(self) -> None:
        async with self._client_condition:
            if self._active_requests <= 0:
                raise RuntimeError("Dolphin query embedding client lease accounting is invalid")
            self._active_requests -= 1
            if self._active_requests == 0:
                self._client_condition.notify_all()


def _default_client(api_key: str) -> _AsyncOpenAIClient:
    return cast(
        _AsyncOpenAIClient,
        AsyncOpenAI(
            api_key=api_key,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        ),
    )


def _require_query(query: str) -> None:
    if not isinstance(query, str) or not 1 <= len(query) <= MAX_QUERY_CHARACTERS:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid")
    try:
        identify_embedding_input(query)
    except ArtifactInputInvalid:
        raise EmbeddingContractViolation("Dolphin query embedding input is invalid") from None


def _vector_from_response(response: object) -> tuple[float, ...]:
    try:
        if getattr(response, "model") != EMBEDDING_MODEL:
            raise EmbeddingContractViolation("Dolphin query embedding response uses an incompatible model")
        data = getattr(response, "data")
        if not isinstance(data, list) or len(data) != 1:
            raise EmbeddingContractViolation("Dolphin query embedding response has invalid cardinality")
        item = data[0]
        if getattr(item, "index") != 0:
            raise EmbeddingContractViolation("Dolphin query embedding response has invalid ordering")
        return canonicalize_embedding_vector(getattr(item, "embedding"))
    except QueryEmbeddingError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise EmbeddingContractViolation("Dolphin query embedding response violates the fixed contract") from None


def _raise_classified(exc: Exception) -> None:
    raise _classified_failure(exc) from None


def _classified_failure(exc: Exception) -> QueryEmbeddingError:
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return CredentialRejected("Dolphin OpenAI credential was rejected")
    if isinstance(exc, (TimeoutError, openai.APITimeoutError)):
        return TransientProviderFailure("timeout")
    if isinstance(exc, openai.RateLimitError):
        return TransientProviderFailure("rate_limited")
    if isinstance(exc, openai.APIConnectionError):
        return TransientProviderFailure("connection")
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        if status == 408:
            return TransientProviderFailure("timeout")
        if status == 429:
            return TransientProviderFailure("rate_limited")
        if status == 409 or status >= 500:
            return TransientProviderFailure("server")
        return PermanentProviderFailure("request_rejected")
    return PermanentProviderFailure("provider_error")


def _safe_retry_delay(exc: Exception, random_source: RandomSource, clock: Clock) -> float:
    try:
        sample = float(random_source())
    except (TypeError, ValueError, OverflowError):
        sample = 0.5
    if not math.isfinite(sample) or not 0 <= sample <= 1:
        sample = 0.5
    jitter = 1 + ((sample * 2) - 1) * _RETRY_JITTER_FRACTION
    delay = _RETRY_DELAY_SECONDS * jitter
    retry_after = _safe_retry_after_seconds(exc, clock())
    if retry_after is not None:
        delay = max(delay, retry_after)
    return min(delay, _MAX_RETRY_DELAY_SECONDS)


def _safe_retry_after_seconds(exc: Exception, observed_at: datetime) -> float | None:
    if not isinstance(exc, openai.APIStatusError):
        return None
    safe_values: list[float] = []
    retry_after = exc.response.headers.get("retry-after")
    if retry_after is not None and len(retry_after) <= 128:
        try:
            value = float(retry_after)
        except (TypeError, ValueError, OverflowError):
            value = _http_date_retry_seconds(retry_after, observed_at)
        if math.isfinite(value) and value >= 0:
            safe_values.append(min(value, _MAX_RETRY_DELAY_SECONDS))
    retry_after_ms = exc.response.headers.get("retry-after-ms")
    if retry_after_ms is not None and len(retry_after_ms) <= 32:
        try:
            value = float(retry_after_ms) * 0.001
        except (TypeError, ValueError, OverflowError):
            value = -1
        if math.isfinite(value) and value >= 0:
            safe_values.append(min(value, _MAX_RETRY_DELAY_SECONDS))
    return max(safe_values, default=None)


def _http_date_retry_seconds(value: str, observed_at: datetime) -> float:
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
        return -1
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return -1
    if retry_at.tzinfo is None:
        return -1
    return (retry_at.astimezone(UTC) - observed_at.astimezone(UTC)).total_seconds()
