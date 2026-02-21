from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from .v1_canonical_schema import apply as _migration_v1_canonical_schema

MigrationFn = Callable[[sqlite3.Connection], str | None]


@dataclass(frozen=True)
class SchemaMigration:
    """Single metadata schema migration step."""

    version: int
    name: str
    apply: MigrationFn


# pb-dolphin 0.2.2 contract:
# - schema v1 is the first and only supported runtime schema
# - schema v0 is bootstrap state used only to trigger one-time startup migration
SCHEMA_MIGRATIONS: tuple[SchemaMigration, ...] = (
    SchemaMigration(
        version=1,
        name="canonical_schema_v1",
        apply=_migration_v1_canonical_schema,
    ),
)

LATEST_SCHEMA_VERSION = 1
