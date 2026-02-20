from __future__ import annotations

import sqlite3
from collections.abc import Iterable


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _fk_has_cascade(conn: sqlite3.Connection, table_name: str, from_col: str, ref_table: str) -> bool:
    rows = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    for row in rows:
        # PRAGMA foreign_key_list columns:
        # id, seq, table, from, to, on_update, on_delete, match
        if str(row[2]) == ref_table and str(row[3]) == from_col:
            return str(row[6]).upper() == "CASCADE"
    return False


def _rebuild_table(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    create_sql: str,
    insert_sql: str,
    index_sql: Iterable[str] = (),
) -> int:
    """Rebuild a table with canonical schema and preserve compatible rows."""
    backup_name = f"{table_name}__legacy_backup"
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {backup_name}")
    cur.execute(f"ALTER TABLE {table_name} RENAME TO {backup_name}")
    cur.execute(create_sql)
    cur.execute(insert_sql.format(old=backup_name))
    inserted = max(cur.rowcount, 0)
    for stmt in index_sql:
        cur.execute(stmt)
    cur.execute(f"DROP TABLE {backup_name}")
    return inserted


def _migrate_code_node_aliases(conn: sqlite3.Connection) -> int:
    """Merge legacy code_node_aliases into canonical node_aliases."""
    if not _table_exists(conn, "code_node_aliases"):
        return 0

    legacy_cols = _table_columns(conn, "code_node_aliases")
    if "node_id" not in legacy_cols or "file_id" not in legacy_cols:
        conn.execute("DROP TABLE code_node_aliases")
        return 0

    if not _table_exists(conn, "node_aliases"):
        conn.execute(
            """
            CREATE TABLE node_aliases (
                id TEXT PRIMARY KEY NOT NULL,
                node_id TEXT NOT NULL REFERENCES code_nodes(id) ON DELETE CASCADE,
                file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                alias_name TEXT NOT NULL,
                alias_qualified_name TEXT NOT NULL,
                line_number INTEGER,
                CONSTRAINT uq_node_alias_identity UNIQUE (node_id, file_id, alias_qualified_name)
            )
            """
        )
        conn.execute("CREATE INDEX ix_node_aliases_name ON node_aliases(alias_name)")
        conn.execute("CREATE INDEX ix_node_aliases_qualified ON node_aliases(alias_qualified_name)")
        conn.execute("CREATE INDEX ix_node_aliases_node ON node_aliases(node_id)")

    id_expr = (
        "COALESCE(CAST(id AS TEXT), lower(hex(randomblob(16))))"
        if "id" in legacy_cols
        else "lower(hex(randomblob(16)))"
    )
    alias_name_expr = (
        "COALESCE(alias_name, alias_qualified_name, node_id)"
        if "alias_name" in legacy_cols and "alias_qualified_name" in legacy_cols
        else (
            "COALESCE(alias_name, node_id)"
            if "alias_name" in legacy_cols
            else ("COALESCE(alias_qualified_name, node_id)" if "alias_qualified_name" in legacy_cols else "node_id")
        )
    )
    alias_qualified_expr = (
        "COALESCE(alias_qualified_name, alias_name, node_id)"
        if "alias_qualified_name" in legacy_cols and "alias_name" in legacy_cols
        else (
            "COALESCE(alias_qualified_name, node_id)"
            if "alias_qualified_name" in legacy_cols
            else ("COALESCE(alias_name, node_id)" if "alias_name" in legacy_cols else "node_id")
        )
    )
    line_expr = "line_number" if "line_number" in legacy_cols else "NULL"

    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT OR IGNORE INTO node_aliases (
            id, node_id, file_id, alias_name, alias_qualified_name, line_number
        )
        SELECT
            {id_expr},
            node_id,
            file_id,
            {alias_name_expr},
            {alias_qualified_expr},
            {line_expr}
        FROM code_node_aliases
        WHERE node_id IS NOT NULL
          AND file_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM code_nodes n WHERE n.id = code_node_aliases.node_id)
          AND EXISTS (SELECT 1 FROM files f WHERE f.id = code_node_aliases.file_id)
        """
    )
    moved = max(cur.rowcount, 0)
    conn.execute("DROP TABLE code_node_aliases")
    return moved


def _rebuild_code_edges_if_needed(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "code_edges"):
        return 0
    if _fk_has_cascade(conn, "code_edges", "source_node_id", "code_nodes") and _fk_has_cascade(
        conn, "code_edges", "target_node_id", "code_nodes"
    ):
        return 0

    cols = _table_columns(conn, "code_edges")
    id_expr = "COALESCE(CAST(id AS TEXT), lower(hex(randomblob(16))))" if "id" in cols else "lower(hex(randomblob(16)))"
    source_expr = "source_node_id" if "source_node_id" in cols else "NULL"
    target_expr = "target_node_id" if "target_node_id" in cols else "NULL"
    edge_type_expr = "COALESCE(edge_type, 'unknown')" if "edge_type" in cols else "'unknown'"
    repo_expr = (
        "COALESCE(repo_id, (SELECT repo_id FROM code_nodes n WHERE n.id = code_edges__legacy_backup.source_node_id))"
        if "repo_id" in cols
        else "(SELECT repo_id FROM code_nodes n WHERE n.id = code_edges__legacy_backup.source_node_id)"
    )
    line_expr = "line_number" if "line_number" in cols else "NULL"
    is_direct_expr = "COALESCE(is_direct, 1)" if "is_direct" in cols else "1"
    rel_expr = "relationship_metadata" if "relationship_metadata" in cols else "NULL"
    commit_expr = "COALESCE(commit_sha, 'unknown')" if "commit_sha" in cols else "'unknown'"
    first_expr = "COALESCE(first_seen_at, datetime('now'))" if "first_seen_at" in cols else "datetime('now')"
    last_expr = "COALESCE(last_seen_at, datetime('now'))" if "last_seen_at" in cols else "datetime('now')"

    return _rebuild_table(
        conn,
        table_name="code_edges",
        create_sql="""
            CREATE TABLE code_edges (
                id TEXT PRIMARY KEY NOT NULL,
                source_node_id TEXT NOT NULL REFERENCES code_nodes(id) ON DELETE CASCADE,
                target_node_id TEXT NOT NULL REFERENCES code_nodes(id) ON DELETE CASCADE,
                edge_type TEXT NOT NULL,
                repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
                line_number INTEGER,
                is_direct INTEGER NOT NULL DEFAULT 1,
                relationship_metadata TEXT,
                commit_sha TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                CONSTRAINT uq_code_edge_identity UNIQUE (source_node_id, target_node_id, edge_type, line_number)
            )
        """,
        insert_sql=f"""
            INSERT OR IGNORE INTO code_edges (
                id, source_node_id, target_node_id, edge_type, repo_id,
                line_number, is_direct, relationship_metadata, commit_sha, first_seen_at, last_seen_at
            )
            SELECT
                {id_expr},
                {source_expr},
                {target_expr},
                {edge_type_expr},
                {repo_expr},
                {line_expr},
                {is_direct_expr},
                {rel_expr},
                {commit_expr},
                {first_expr},
                {last_expr}
            FROM {{old}} AS code_edges__legacy_backup
            WHERE {source_expr} IS NOT NULL
              AND {target_expr} IS NOT NULL
              AND {repo_expr} IS NOT NULL
              AND EXISTS (SELECT 1 FROM code_nodes n WHERE n.id = {source_expr})
              AND EXISTS (SELECT 1 FROM code_nodes n WHERE n.id = {target_expr})
              AND EXISTS (SELECT 1 FROM repos r WHERE r.id = {repo_expr})
        """,
        index_sql=(
            "CREATE INDEX ix_code_edges_source ON code_edges(source_node_id, edge_type)",
            "CREATE INDEX ix_code_edges_target ON code_edges(target_node_id, edge_type)",
            "CREATE INDEX ix_code_edges_type ON code_edges(edge_type)",
            "CREATE INDEX ix_code_edges_bidirectional ON code_edges(source_node_id, target_node_id)",
            "CREATE INDEX ix_code_edges_source_type_target ON code_edges(source_node_id, edge_type, target_node_id)",
            "CREATE INDEX ix_code_edges_target_type_source ON code_edges(target_node_id, edge_type, source_node_id)",
        ),
    )


def _rebuild_node_aliases_if_needed(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "node_aliases"):
        return 0
    if _fk_has_cascade(conn, "node_aliases", "node_id", "code_nodes") and _fk_has_cascade(
        conn, "node_aliases", "file_id", "files"
    ):
        return 0

    cols = _table_columns(conn, "node_aliases")
    id_expr = "COALESCE(CAST(id AS TEXT), lower(hex(randomblob(16))))" if "id" in cols else "lower(hex(randomblob(16)))"
    node_expr = "node_id" if "node_id" in cols else "NULL"
    file_expr = "file_id" if "file_id" in cols else "NULL"
    alias_name_expr = (
        "COALESCE(alias_name, alias_qualified_name, node_id)"
        if "alias_name" in cols
        else "COALESCE(alias_qualified_name, node_id)"
    )
    alias_q_expr = (
        "COALESCE(alias_qualified_name, alias_name, node_id)"
        if "alias_qualified_name" in cols and "alias_name" in cols
        else (
            "COALESCE(alias_qualified_name, node_id)"
            if "alias_qualified_name" in cols
            else "COALESCE(alias_name, node_id)"
        )
    )
    line_expr = "line_number" if "line_number" in cols else "NULL"

    return _rebuild_table(
        conn,
        table_name="node_aliases",
        create_sql="""
            CREATE TABLE node_aliases (
                id TEXT PRIMARY KEY NOT NULL,
                node_id TEXT NOT NULL REFERENCES code_nodes(id) ON DELETE CASCADE,
                file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                alias_name TEXT NOT NULL,
                alias_qualified_name TEXT NOT NULL,
                line_number INTEGER,
                CONSTRAINT uq_node_alias_identity UNIQUE (node_id, file_id, alias_qualified_name)
            )
        """,
        insert_sql=f"""
            INSERT OR IGNORE INTO node_aliases (
                id, node_id, file_id, alias_name, alias_qualified_name, line_number
            )
            SELECT
                {id_expr},
                {node_expr},
                {file_expr},
                {alias_name_expr},
                {alias_q_expr},
                {line_expr}
            FROM {{old}} AS node_aliases__legacy_backup
            WHERE {node_expr} IS NOT NULL
              AND {file_expr} IS NOT NULL
              AND EXISTS (SELECT 1 FROM code_nodes n WHERE n.id = {node_expr})
              AND EXISTS (SELECT 1 FROM files f WHERE f.id = {file_expr})
        """,
        index_sql=(
            "CREATE INDEX ix_node_aliases_name ON node_aliases(alias_name)",
            "CREATE INDEX ix_node_aliases_qualified ON node_aliases(alias_qualified_name)",
            "CREATE INDEX ix_node_aliases_node ON node_aliases(node_id)",
        ),
    )


def _rebuild_cross_repo_references_if_needed(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "cross_repo_references"):
        return 0
    if (
        _fk_has_cascade(conn, "cross_repo_references", "source_node_id", "code_nodes")
        and _fk_has_cascade(conn, "cross_repo_references", "source_repo_id", "repos")
        and _fk_has_cascade(conn, "cross_repo_references", "file_id", "files")
    ):
        return 0

    cols = _table_columns(conn, "cross_repo_references")
    id_expr = "COALESCE(CAST(id AS TEXT), lower(hex(randomblob(16))))" if "id" in cols else "lower(hex(randomblob(16)))"
    source_node_expr = "source_node_id" if "source_node_id" in cols else "NULL"
    source_repo_expr = (
        (
            "COALESCE("
            "source_repo_id, "
            "(SELECT repo_id FROM code_nodes n "
            "WHERE n.id = cross_repo_references__legacy_backup.source_node_id)"
            ")"
        )
        if "source_repo_id" in cols
        else "(SELECT repo_id FROM code_nodes n WHERE n.id = cross_repo_references__legacy_backup.source_node_id)"
    )
    pkg_expr = "COALESCE(target_package, 'unknown')" if "target_package" in cols else "'unknown'"
    mod_expr = "target_module" if "target_module" in cols else "NULL"
    sym_expr = "target_symbol" if "target_symbol" in cols else "NULL"
    ref_expr = "COALESCE(reference_type, 'import')" if "reference_type" in cols else "'import'"
    file_expr = "file_id" if "file_id" in cols else "NULL"
    line_expr = "line_number" if "line_number" in cols else "NULL"
    first_expr = "COALESCE(first_seen_at, datetime('now'))" if "first_seen_at" in cols else "datetime('now')"
    last_expr = "COALESCE(last_seen_at, datetime('now'))" if "last_seen_at" in cols else "datetime('now')"

    return _rebuild_table(
        conn,
        table_name="cross_repo_references",
        create_sql="""
            CREATE TABLE cross_repo_references (
                id TEXT PRIMARY KEY NOT NULL,
                source_node_id TEXT NOT NULL REFERENCES code_nodes(id) ON DELETE CASCADE,
                source_repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
                target_package TEXT NOT NULL,
                target_module TEXT,
                target_symbol TEXT,
                reference_type TEXT NOT NULL,
                file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                line_number INTEGER,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
        """,
        insert_sql=f"""
            INSERT OR IGNORE INTO cross_repo_references (
                id, source_node_id, source_repo_id, target_package, target_module,
                target_symbol, reference_type, file_id, line_number, first_seen_at, last_seen_at
            )
            SELECT
                {id_expr},
                {source_node_expr},
                {source_repo_expr},
                {pkg_expr},
                {mod_expr},
                {sym_expr},
                {ref_expr},
                {file_expr},
                {line_expr},
                {first_expr},
                {last_expr}
            FROM {{old}} AS cross_repo_references__legacy_backup
            WHERE {source_node_expr} IS NOT NULL
              AND {source_repo_expr} IS NOT NULL
              AND {file_expr} IS NOT NULL
              AND EXISTS (SELECT 1 FROM code_nodes n WHERE n.id = {source_node_expr})
              AND EXISTS (SELECT 1 FROM repos r WHERE r.id = {source_repo_expr})
              AND EXISTS (SELECT 1 FROM files f WHERE f.id = {file_expr})
        """,
        index_sql=(
            "CREATE INDEX ix_cross_repo_source ON cross_repo_references(source_node_id)",
            "CREATE INDEX ix_cross_repo_package ON cross_repo_references(target_package, target_module)",
        ),
    )


def _rebuild_graph_metrics_if_needed(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "graph_metrics"):
        return 0
    if _fk_has_cascade(conn, "graph_metrics", "node_id", "code_nodes"):
        return 0

    cols = _table_columns(conn, "graph_metrics")
    node_expr = "node_id" if "node_id" in cols else "NULL"
    pagerank_expr = "pagerank" if "pagerank" in cols else "NULL"
    bc_expr = "betweenness_centrality" if "betweenness_centrality" in cols else "NULL"
    in_expr = "COALESCE(in_degree, 0)" if "in_degree" in cols else "0"
    out_expr = "COALESCE(out_degree, 0)" if "out_degree" in cols else "0"
    cc_expr = "cyclomatic_complexity" if "cyclomatic_complexity" in cols else "NULL"
    community_expr = "community_id" if "community_id" in cols else "NULL"

    return _rebuild_table(
        conn,
        table_name="graph_metrics",
        create_sql="""
            CREATE TABLE graph_metrics (
                node_id TEXT PRIMARY KEY NOT NULL REFERENCES code_nodes(id) ON DELETE CASCADE,
                pagerank REAL,
                betweenness_centrality REAL,
                in_degree INTEGER NOT NULL DEFAULT 0,
                out_degree INTEGER NOT NULL DEFAULT 0,
                cyclomatic_complexity INTEGER,
                community_id INTEGER
            )
        """,
        insert_sql=f"""
            INSERT OR IGNORE INTO graph_metrics (
                node_id, pagerank, betweenness_centrality,
                in_degree, out_degree, cyclomatic_complexity, community_id
            )
            SELECT
                {node_expr},
                {pagerank_expr},
                {bc_expr},
                {in_expr},
                {out_expr},
                {cc_expr},
                {community_expr}
            FROM {{old}} AS graph_metrics__legacy_backup
            WHERE {node_expr} IS NOT NULL
              AND EXISTS (SELECT 1 FROM code_nodes n WHERE n.id = {node_expr})
        """,
        index_sql=(
            "CREATE INDEX ix_graph_metrics_pagerank ON graph_metrics(pagerank)",
            "CREATE INDEX ix_graph_metrics_community ON graph_metrics(community_id)",
        ),
    )


def _rebuild_file_snapshots_if_needed(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "file_snapshots"):
        return 0
    if _fk_has_cascade(conn, "file_snapshots", "file_id", "files") and _fk_has_cascade(
        conn, "file_snapshots", "repo_id", "repos"
    ):
        return 0

    cols = _table_columns(conn, "file_snapshots")
    file_expr = "file_id" if "file_id" in cols else "NULL"
    repo_expr = (
        "COALESCE(repo_id, (SELECT repo_id FROM files f WHERE f.id = file_snapshots__legacy_backup.file_id))"
        if "repo_id" in cols
        else "(SELECT repo_id FROM files f WHERE f.id = file_snapshots__legacy_backup.file_id)"
    )
    path_expr = (
        "COALESCE(path, (SELECT path FROM files f WHERE f.id = file_snapshots__legacy_backup.file_id))"
        if "path" in cols
        else "(SELECT path FROM files f WHERE f.id = file_snapshots__legacy_backup.file_id)"
    )
    mtime_expr = "COALESCE(mtime_ns, 0)" if "mtime_ns" in cols else "0"
    size_expr = "COALESCE(size_bytes, 0)" if "size_bytes" in cols else "0"
    hash_expr = "COALESCE(content_hash, '')" if "content_hash" in cols else "''"
    indexed_expr = "COALESCE(last_indexed_at, datetime('now'))" if "last_indexed_at" in cols else "datetime('now')"

    return _rebuild_table(
        conn,
        table_name="file_snapshots",
        create_sql="""
            CREATE TABLE file_snapshots (
                file_id INTEGER PRIMARY KEY NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                last_indexed_at TEXT NOT NULL,
                CONSTRAINT uq_file_snapshot_repo_path UNIQUE (repo_id, path)
            )
        """,
        insert_sql=f"""
            INSERT OR IGNORE INTO file_snapshots (
                file_id, repo_id, path, mtime_ns, size_bytes, content_hash, last_indexed_at
            )
            SELECT
                {file_expr},
                {repo_expr},
                {path_expr},
                {mtime_expr},
                {size_expr},
                {hash_expr},
                {indexed_expr}
            FROM {{old}} AS file_snapshots__legacy_backup
            WHERE {file_expr} IS NOT NULL
              AND {repo_expr} IS NOT NULL
              AND EXISTS (SELECT 1 FROM files f WHERE f.id = {file_expr})
              AND EXISTS (SELECT 1 FROM repos r WHERE r.id = {repo_expr})
        """,
        index_sql=("CREATE INDEX idx_file_snapshots_repo ON file_snapshots(repo_id)",),
    )


def apply(conn: sqlite3.Connection) -> str:
    """Canonicalize legacy metadata tables and FK cascade behavior."""
    moved_legacy_alias_rows = _migrate_code_node_aliases(conn)
    rebuilt: list[str] = []
    rows_migrated = 0

    rebuilt_code_edges = _rebuild_code_edges_if_needed(conn)
    if rebuilt_code_edges:
        rebuilt.append("code_edges")
        rows_migrated += rebuilt_code_edges

    rebuilt_node_aliases = _rebuild_node_aliases_if_needed(conn)
    if rebuilt_node_aliases:
        rebuilt.append("node_aliases")
        rows_migrated += rebuilt_node_aliases

    rebuilt_cross_repo = _rebuild_cross_repo_references_if_needed(conn)
    if rebuilt_cross_repo:
        rebuilt.append("cross_repo_references")
        rows_migrated += rebuilt_cross_repo

    rebuilt_graph_metrics = _rebuild_graph_metrics_if_needed(conn)
    if rebuilt_graph_metrics:
        rebuilt.append("graph_metrics")
        rows_migrated += rebuilt_graph_metrics

    rebuilt_file_snapshots = _rebuild_file_snapshots_if_needed(conn)
    if rebuilt_file_snapshots:
        rebuilt.append("file_snapshots")
        rows_migrated += rebuilt_file_snapshots

    summary_parts = []
    if moved_legacy_alias_rows:
        summary_parts.append(f"migrated {moved_legacy_alias_rows} legacy code_node_aliases rows")
    if rebuilt:
        summary_parts.append(f"rebuilt tables: {', '.join(rebuilt)}")
    if rows_migrated:
        summary_parts.append(f"{rows_migrated} rows preserved")
    if not summary_parts:
        summary_parts.append("no canonicalization changes were required")

    return "; ".join(summary_parts)
