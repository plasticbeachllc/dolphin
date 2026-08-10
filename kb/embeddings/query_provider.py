"""Bounded OpenAI adapter for the fixed query-embedding contract."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
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


class OpenAIQueryEmbeddingProvider:
    """Make one redacted, fixed-model request under a short retry budget."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        client_factory: ClientFactory | None = None,
        sleep: AsyncSleep = asyncio.sleep,
    ) -> None:
        self._environment = os.environ if environment is None else environment
        self._client_factory = client_factory or _default_client
        self._sleep = sleep
        self._client: _AsyncOpenAIClient | None = None

    async def embed_query(self, query: str) -> tuple[float, ...]:
        """Return one canonical vector or a closed, safe failure category."""
        _require_query(query)
        api_key = self._environment.get(DOLPHIN_OPENAI_API_KEY, "").strip()
        if not api_key:
            raise CredentialMissing("Dolphin requires DOLPHIN_OPENAI_API_KEY in the MCP server environment")
        client = self._client
        if client is None:
            try:
                client = self._client_factory(api_key)
            except Exception as exc:
                _raise_classified(exc)
            self._client = client
        assert client is not None

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
                    await self._sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise failure from None
        raise PermanentProviderFailure("provider_error")

    async def close(self) -> None:
        """Release the lazily created SDK client without retaining credential state."""
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.close()
        except Exception:
            raise PermanentProviderFailure("provider_error") from None


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
