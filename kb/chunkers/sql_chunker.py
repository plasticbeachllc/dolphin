"""SQL chunker with regex-based parsing for robust handling.

This module chunks SQL source files into logical units using regex patterns.
Supports:
- Standard SQL DDL (CREATE TABLE, VIEW, FUNCTION, PROCEDURE, TRIGGER, INDEX)
- Multiple SQL dialects (PostgreSQL, MySQL, SQLite)
- SQLMesh MODEL() declarations
- dbt models and macros (with Jinja template handling)
- Accurate line number tracking

Architecture:
- Regex-based statement splitting (handles PostgreSQL dollar quotes)
- Pattern matching for entity classification
- Preserves exact formatting and line numbers for citations
- Graph node/edge extraction for code graph enhancement
"""

from __future__ import annotations

import logging
import re

from .graph_types import GraphEdge, GraphNode
from .token_utils import count_tokens, get_tokenizer
from .types import Chunk

_log = logging.getLogger(__name__)

__all__ = ["chunk_source", "detect_sql_dialect", "extract_graph_data"]

# SQL dialect detection patterns
SQL_DIALECTS = {
    "postgres": ["SERIAL", "BIGSERIAL", "RETURNING", "::", "ILIKE", "PLPGSQL"],
    "mysql": ["AUTO_INCREMENT", "TINYINT", "MEDIUMINT", "FULLTEXT"],
    "sqlite": ["AUTOINCREMENT", "WITHOUT ROWID"],
}


def detect_sql_dialect(source: str) -> str:
    """Detect SQL dialect from source code.

    Args:
        source: SQL source code

    Returns:
        Dialect identifier: 'postgres', 'mysql', 'sqlite', or 'generic'
    """
    source_upper = source.upper()

    for dialect, keywords in SQL_DIALECTS.items():
        if any(keyword in source_upper for keyword in keywords):
            return dialect

    return "generic"


def chunk_source(
    source: str,
    *,
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> list[Chunk]:
    """Chunk SQL source into logical units.

    Chunking strategy:
    - Each CREATE TABLE/VIEW/FUNCTION/PROCEDURE as separate chunk
    - Each SQLMesh MODEL() declaration as separate chunk
    - Each dbt model/macro as separate chunk
    - Large queries broken into manageable pieces
    - CTEs chunked as units

    Args:
        source: SQL source code
        model: Tokenizer model ("small" or "large")
        token_target: Target tokens per chunk
        overlap_pct: Overlap percentage (not used for SQL, kept for API compatibility)

    Returns:
        List of Chunk objects with SQL metadata
    """
    if not source or not source.strip():
        return []

    # Detect dialect for metadata
    dialect = detect_sql_dialect(source)
    _log.debug("Detected SQL dialect: %s", dialect)

    chunks = []
    tok = get_tokenizer(model)

    # Split source into statements
    statements = _split_sql_statements(source)

    current_line = 1
    for statement in statements:
        if not statement.strip():
            current_line += statement.count("\n")
            continue

        # Classify statement and extract entity name
        statement_type, entity_name = _classify_statement(statement)

        # Calculate line numbers
        start_line = current_line
        end_line = current_line + statement.count("\n")

        # Extract chunk text
        chunk_text = statement.strip()
        token_count = count_tokens(chunk_text, tok)

        # If too large, break into smaller pieces
        if token_count > token_target * 1.5:
            sub_chunks = _chunk_large_statement(
                chunk_text,
                start_line,
                model=model,
                token_target=token_target,
                statement_type=statement_type,
                entity_name=entity_name,
            )
            chunks.extend(sub_chunks)
        else:
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_line=start_line,
                    end_line=end_line,
                    token_count=token_count,
                    symbol_kind=statement_type,
                    symbol_name=entity_name,
                    symbol_path=entity_name,
                )
            )

        current_line = end_line + 1

    _log.info("Chunked SQL into %d chunks (dialect: %s)", len(chunks), dialect)
    return chunks


def _split_sql_statements(source: str) -> list[str]:
    """Split SQL source into individual statements.

    Handles:
    - Semicolon-terminated statements
    - Statements with string literals containing semicolons
    - PostgreSQL dollar-quoted strings ($$...$$)
    - Multi-line statements
    - dbt Jinja blocks ({% ... %})
    - SQLMesh MODEL() declarations

    Returns:
        List of statement strings (with original whitespace preserved)
    """
    statements = []
    current = []
    in_string = False
    string_char = None
    in_jinja_block = False
    in_dollar_quote = False
    dollar_quote_tag = None

    lines = source.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Track Jinja blocks (dbt)
        if "{%" in line and not in_dollar_quote:
            in_jinja_block = True
        if "%}" in line and not in_dollar_quote:
            in_jinja_block = False

        # Track dollar-quoted strings (PostgreSQL: $$...$$, $tag$...$tag$)
        j = 0
        while j < len(line):
            char = line[j]

            # Handle escape sequences in regular strings
            if j > 0 and line[j - 1] == "\\" and in_string:
                j += 1
                continue

            # Dollar quote detection
            if char == "$" and not in_string:
                # Look ahead for potential dollar quote
                dollar_match = re.match(r"\$([A-Za-z_]*)\$", line[j:])
                if dollar_match:
                    quote_tag = dollar_match.group(1)
                    if not in_dollar_quote:
                        # Start of dollar quote
                        in_dollar_quote = True
                        dollar_quote_tag = quote_tag
                        j += len(dollar_match.group(0))
                        continue
                    elif quote_tag == dollar_quote_tag:
                        # End of dollar quote
                        in_dollar_quote = False
                        dollar_quote_tag = None
                        j += len(dollar_match.group(0))
                        continue

            # Regular string tracking (only if not in dollar quote)
            if not in_dollar_quote:
                if char in ('"', "'") and not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char and in_string:
                    in_string = False
                    string_char = None

            j += 1

        current.append(line)

        # Check for statement terminator (semicolon outside strings, dollar quotes, and Jinja blocks)
        if ";" in line and not in_string and not in_jinja_block and not in_dollar_quote:
            statements.append("\n".join(current))
            current = []

        i += 1

    # Add any remaining content
    if current:
        statements.append("\n".join(current))

    return statements


def _classify_statement(statement: str) -> tuple[str, str | None]:
    """Classify SQL statement and extract entity name.

    Supports:
    - Standard SQL DDL (CREATE TABLE, VIEW, FUNCTION, etc.)
    - SQLMesh MODEL() declarations
    - dbt models ({% model %} blocks)
    - dbt macros ({% macro %} blocks)
    - CTEs and queries

    Returns:
        (statement_type, entity_name) tuple
    """
    statement_upper = statement.upper().strip()

    # SQLMesh MODEL() declaration
    # Example: MODEL(name="user_analytics", ...)
    sqlmesh_match = re.search(
        r'MODEL\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', statement, re.IGNORECASE
    )
    if sqlmesh_match:
        model_name = sqlmesh_match.group(1)
        return "sqlmesh_model", model_name

    # dbt model block
    # Example: {% model name="user_analytics" %}
    dbt_model_match = re.search(
        r'\{%\s*model\s+name\s*=\s*["\']([^"\']+)["\']', statement, re.IGNORECASE
    )
    if dbt_model_match:
        model_name = dbt_model_match.group(1)
        return "dbt_model", model_name

    # dbt macro
    # Example: {% macro calculate_total(column_name) %}
    dbt_macro_match = re.search(
        r"\{%\s*macro\s+([A-Za-z_][A-Za-z0-9_]*)", statement, re.IGNORECASE
    )
    if dbt_macro_match:
        macro_name = dbt_macro_match.group(1)
        return "dbt_macro", macro_name

    # Standard SQL CREATE statements
    # Support both regular identifiers and backtick/quote-delimited identifiers
    create_match = re.search(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?"
        r"(TABLE|VIEW|FUNCTION|PROCEDURE|TRIGGER|INDEX)\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?"
        r'[`"\']?([a-zA-Z0-9_.]+)[`"\']?',
        statement,  # Use original statement to preserve backticks
        re.IGNORECASE,
    )
    if create_match:
        entity_type = create_match.group(1).lower()
        entity_name = create_match.group(2).lower()
        return entity_type, entity_name

    # SELECT/INSERT/UPDATE/DELETE queries
    for query_type in ["SELECT", "INSERT", "UPDATE", "DELETE"]:
        if statement_upper.startswith(query_type):
            return "query", None

    # WITH (CTE)
    if statement_upper.startswith("WITH"):
        # Try to extract CTE name
        cte_match = re.search(r"WITH\s+(\w+)\s+AS", statement_upper)
        cte_name = cte_match.group(1).lower() if cte_match else None
        return "cte", cte_name

    return "statement", None


def _chunk_large_statement(
    statement: str,
    start_line: int,
    model: str,
    token_target: int,
    statement_type: str,
    entity_name: str | None,
) -> list[Chunk]:
    """Break large SQL statement into smaller chunks.

    Uses simple line-based chunking with respect to token limits.
    Preserves statement_type and entity_name metadata.
    """
    lines = statement.split("\n")
    chunks = []
    current_chunk = []
    current_line = start_line
    tok = get_tokenizer(model)

    for line in lines:
        current_chunk.append(line)
        chunk_text = "\n".join(current_chunk)

        if count_tokens(chunk_text, tok) > token_target:
            if len(current_chunk) > 1:
                # Save previous chunk
                prev_text = "\n".join(current_chunk[:-1])
                chunks.append(
                    Chunk(
                        text=prev_text,
                        start_line=current_line,
                        end_line=current_line + len(current_chunk) - 2,
                        token_count=count_tokens(prev_text, tok),
                        symbol_kind=f"{statement_type}_part",
                        symbol_name=entity_name,
                        symbol_path=entity_name,
                    )
                )
                current_line += len(current_chunk) - 1
                current_chunk = [line]

    # Add final chunk
    if current_chunk:
        chunk_text = "\n".join(current_chunk)
        chunks.append(
            Chunk(
                text=chunk_text,
                start_line=current_line,
                end_line=current_line + len(current_chunk) - 1,
                token_count=count_tokens(chunk_text, tok),
                symbol_kind=f"{statement_type}_part",
                symbol_name=entity_name,
                symbol_path=entity_name,
            )
        )

    return chunks


def extract_graph_data(source: str) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Extract graph nodes and edges from SQL source for code graph.

    Nodes:
    - Tables, views, functions, procedures, triggers
    - SQLMesh models
    - dbt models and macros

    Edges:
    - Table references (FROM/JOIN clauses)
    - Function calls
    - View dependencies
    - SQLMesh model dependencies (depends_on)
    - dbt macro calls ({{ macro_name() }})
    - dbt ref() and source() dependencies

    Args:
        source: SQL source code

    Returns:
        Tuple of (nodes, edges) for graph database insertion
    """
    nodes = []
    edges = []

    statements = _split_sql_statements(source)
    current_line = 1

    for statement in statements:
        if not statement.strip():
            current_line += statement.count("\n")
            continue

        stmt_type, entity_name = _classify_statement(statement)
        end_line = current_line + statement.count("\n")

        # Create graph node for entity definitions
        if (
            stmt_type
            in [
                "table",
                "view",
                "function",
                "procedure",
                "trigger",
                "sqlmesh_model",
                "dbt_model",
                "dbt_macro",
            ]
            and entity_name
        ):
            nodes.append(
                GraphNode(
                    node_type=stmt_type,
                    name=entity_name,
                    qualified_name=entity_name,  # Could be enhanced with schema
                    start_line=current_line,
                    end_line=end_line,
                )
            )

            # Extract dependencies (edges)

            # 1. Table references (FROM/JOIN)
            if stmt_type in ["view", "function", "query", "cte", "dbt_model"]:
                referenced_tables = _extract_table_references(statement)
                for table in referenced_tables:
                    edges.append(
                        GraphEdge(
                            source_name=entity_name or "<query>",
                            target_name=table,
                            edge_type="references_table",
                            line_number=current_line,
                        )
                    )

            # 2. SQLMesh dependencies (depends_on attribute)
            if stmt_type == "sqlmesh_model":
                depends = _extract_sqlmesh_dependencies(statement)
                for dep in depends:
                    edges.append(
                        GraphEdge(
                            source_name=entity_name,
                            target_name=dep,
                            edge_type="depends_on",
                            line_number=current_line,
                        )
                    )

            # 3. dbt ref() and source() dependencies
            if stmt_type == "dbt_model":
                dbt_refs = _extract_dbt_refs(statement)
                for ref in dbt_refs:
                    edges.append(
                        GraphEdge(
                            source_name=entity_name,
                            target_name=ref,
                            edge_type="depends_on",
                            line_number=current_line,
                        )
                    )

                dbt_sources = _extract_dbt_sources(statement)
                for src in dbt_sources:
                    edges.append(
                        GraphEdge(
                            source_name=entity_name,
                            target_name=src,
                            edge_type="depends_on",
                            line_number=current_line,
                        )
                    )

            # 4. dbt macro calls
            if stmt_type in ["dbt_model", "dbt_macro"]:
                macro_calls = _extract_dbt_macro_calls(statement)
                for macro in macro_calls:
                    edges.append(
                        GraphEdge(
                            source_name=entity_name or "<query>",
                            target_name=macro,
                            edge_type="uses_macro",
                            line_number=current_line,
                        )
                    )

        current_line = end_line + 1

    _log.debug("Extracted %d graph nodes and %d edges from SQL", len(nodes), len(edges))
    return nodes, edges


def _extract_table_references(sql: str) -> list[str]:
    """Extract table names from FROM and JOIN clauses.

    Handles:
    - Simple table names
    - Schema-qualified names (schema.table)
    - Table aliases
    """
    # Match FROM and JOIN clauses
    pattern = r"(?:FROM|JOIN)\s+([\w.]+)"
    matches = re.findall(pattern, sql, re.IGNORECASE)

    # Clean up: remove aliases, extract table name
    tables = []
    for match in matches:
        # Remove quotes
        table = match.strip("`\"'")
        # Take first part if aliased (e.g., "users u" -> "users")
        table = table.split()[0] if " " in table else table
        tables.append(table.lower())

    return list(set(tables))  # Deduplicate


def _extract_sqlmesh_dependencies(sql: str) -> list[str]:
    """Extract SQLMesh model dependencies from depends_on attribute.

    Example:
        MODEL(
            name="user_analytics",
            depends_on=["raw_users", "raw_events"]
        )
    """
    # Match depends_on list
    pattern = r"depends_on\s*=\s*\[([^\]]+)\]"
    match = re.search(pattern, sql, re.IGNORECASE)

    if not match:
        return []

    # Extract model names from list
    deps_str = match.group(1)
    # Match quoted strings
    deps = re.findall(r'["\']([^"\']+)["\']', deps_str)

    return deps


def _extract_dbt_refs(sql: str) -> list[str]:
    """Extract dbt ref() dependencies.

    Example: {{ ref('users') }} -> ['users']
    """
    # Match {{ ref('model_name') }} or {{ ref("model_name") }}
    pattern = r'\{\{\s*ref\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\}\}'
    matches = re.findall(pattern, sql, re.IGNORECASE)
    return matches


def _extract_dbt_sources(sql: str) -> list[str]:
    """Extract dbt source() dependencies.

    Example: {{ source('raw', 'users') }} -> ['raw.users']
    """
    # Match {{ source('schema', 'table') }}
    pattern = r'\{\{\s*source\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)\s*\}\}'
    matches = re.findall(pattern, sql, re.IGNORECASE)

    # Combine schema.table
    return [f"{schema}.{table}" for schema, table in matches]


def _extract_dbt_macro_calls(sql: str) -> list[str]:
    """Extract dbt macro calls.

    Example: {{ calculate_total(amount) }} -> ['calculate_total']

    Excludes built-in Jinja and dbt macros (ref, source, config, etc.)
    """
    # Match {{ macro_name(...) }}
    pattern = r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\("
    matches = re.findall(pattern, sql)

    # Filter out built-in macros
    builtin_macros = {"ref", "source", "config", "var", "env_var", "log", "run_query"}
    custom_macros = [m for m in matches if m.lower() not in builtin_macros]

    return list(set(custom_macros))  # Deduplicate
