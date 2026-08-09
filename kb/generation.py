"""Backend-neutral atomic generation publication contracts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kb.lifecycle_limits import ENTITY_ID_MAX_LENGTH, OPERATION_ID_MAX_LENGTH
from kb.services.workspace_registry import OperationLease

GenerationState = Literal["staging", "ready", "published"]
EMBEDDING_PROVIDER = "openai"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1_536
EMBEDDING_CONTRACT_VERSION = 1


class GenerationCoordinatorError(RuntimeError):
    """Generation visibility could not be changed or inspected safely."""


class GenerationConflict(GenerationCoordinatorError):
    """The expected published generation no longer matches current state."""


class GenerationReadLeaseUnavailable(GenerationCoordinatorError):
    """A read lease is missing, expired, or no longer matches its snapshot."""


class _GenerationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class VerifiedVectorCommit(_GenerationModel):
    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    backend_token: str = Field(min_length=1, max_length=256)
    manifest_digest: str = Field(min_length=1, max_length=256)
    row_count: int = Field(ge=0)
    provider: Literal["openai"] = EMBEDDING_PROVIDER
    model: Literal["text-embedding-3-small"] = EMBEDDING_MODEL
    dimensions: Literal[1_536] = EMBEDDING_DIMENSIONS
    contract_version: Literal[1] = EMBEDDING_CONTRACT_VERSION


class VerifiedGenerationManifest(_GenerationModel):
    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_count: int = Field(ge=0)
    artifact_utf8_bytes: int = Field(ge=0)
    metadata_item_count: int = Field(ge=0)
    keyword_item_count: int = Field(ge=0)
    vector_row_count: int = Field(ge=0)


class StagingGeneration(_GenerationModel):
    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    operation_id: str = Field(min_length=1, max_length=OPERATION_ID_MAX_LENGTH)
    workspace_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    target_fingerprint: str = Field(min_length=1, max_length=256)
    pipeline_key: str = Field(min_length=1, max_length=256)
    state: GenerationState
    vector_commit_token: str | None = Field(default=None, min_length=1, max_length=256)
    vector_digest: str | None = Field(default=None, min_length=1, max_length=256)
    vector_row_count: int | None = Field(default=None, ge=0)
    vector_provider: Literal["openai"] | None = None
    vector_model: Literal["text-embedding-3-small"] | None = None
    vector_dimensions: Literal[1_536] | None = None
    embedding_contract_version: Literal[1] | None = None
    manifest_id: str | None = Field(default=None, min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_digest: str | None = Field(default=None, min_length=1, max_length=256)
    metadata_item_count: int | None = Field(default=None, ge=0)
    keyword_item_count: int | None = Field(default=None, ge=0)
    previous_generation_id: str | None = Field(default=None, min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    created_at: datetime
    ready_at: datetime | None = None
    published_at: datetime | None = None

    @field_validator("created_at", "ready_at", "published_at")
    @classmethod
    def timestamps_are_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("generation timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def component_state_is_complete(self) -> StagingGeneration:
        vector_values = (
            self.vector_commit_token,
            self.vector_digest,
            self.vector_row_count,
            self.vector_provider,
            self.vector_model,
            self.vector_dimensions,
            self.embedding_contract_version,
        )
        manifest_values = (
            self.manifest_id,
            self.manifest_digest,
            self.metadata_item_count,
            self.keyword_item_count,
        )
        if any(value is not None for value in vector_values) and not all(value is not None for value in vector_values):
            raise ValueError("vector readiness fields must be complete")
        if self.state == "staging":
            if (
                any(value is not None for value in manifest_values)
                or self.ready_at is not None
                or self.published_at is not None
            ):
                raise ValueError("staging generation cannot contain a complete manifest")
        elif not all(value is not None for value in (*vector_values, *manifest_values)) or self.ready_at is None:
            raise ValueError("ready generation requires verified components and a manifest")
        if (self.state == "published") != (self.published_at is not None):
            raise ValueError("published timestamp must match generation state")
        if self.state != "published" and self.previous_generation_id is not None:
            raise ValueError("only a published generation can record its predecessor")
        return self


class PublishedSnapshot(_GenerationModel):
    publication_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    generation_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    workspace_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    operation_id: str = Field(min_length=1, max_length=OPERATION_ID_MAX_LENGTH)
    target_fingerprint: str = Field(min_length=1, max_length=256)
    pipeline_key: str = Field(min_length=1, max_length=256)
    manifest_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    manifest_digest: str = Field(min_length=1, max_length=256)
    vector_commit_token: str = Field(min_length=1, max_length=256)
    vector_digest: str = Field(min_length=1, max_length=256)
    vector_row_count: int = Field(ge=0)
    vector_provider: Literal["openai"]
    vector_model: Literal["text-embedding-3-small"]
    vector_dimensions: Literal[1_536]
    embedding_contract_version: Literal[1]
    metadata_item_count: int = Field(ge=0)
    keyword_item_count: int = Field(ge=0)
    revision: int = Field(ge=1)
    published_at: datetime

    @field_validator("published_at")
    @classmethod
    def timestamp_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("publication timestamp must be timezone-aware")
        return value


class GenerationReadLease(_GenerationModel):
    """Pin logical visibility; physical GC must treat the durable lease row as a root."""

    lease_id: str = Field(min_length=1, max_length=ENTITY_ID_MAX_LENGTH)
    snapshot: PublishedSnapshot
    acquired_at: datetime
    expires_at: datetime

    @field_validator("acquired_at", "expires_at")
    @classmethod
    def timestamps_are_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generation read lease timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def expiry_follows_acquisition(self) -> GenerationReadLease:
        if self.expires_at <= self.acquired_at:
            raise ValueError("generation read lease expiry must follow acquisition")
        return self


class GenerationCoordinator(Protocol):
    """Publication authority; readers require GC to honor unexpired lease roots."""

    def create_staging(self, lease: OperationLease) -> StagingGeneration: ...

    def record_vector_ready(
        self,
        lease: OperationLease,
        commit: VerifiedVectorCommit,
    ) -> StagingGeneration: ...

    def mark_ready(
        self,
        lease: OperationLease,
        manifest: VerifiedGenerationManifest,
    ) -> StagingGeneration: ...

    def publish(
        self,
        lease: OperationLease,
        generation_id: str,
        *,
        expected_previous_generation_id: str | None,
    ) -> PublishedSnapshot: ...

    def current_snapshot(self, workspace_id: str) -> PublishedSnapshot | None: ...

    def acquire_read(
        self,
        workspace_id: str,
        *,
        lease_duration: timedelta,
    ) -> GenerationReadLease: ...

    def snapshot_for_lease(self, lease_id: str) -> PublishedSnapshot: ...

    def release_read(self, lease: GenerationReadLease) -> None: ...
