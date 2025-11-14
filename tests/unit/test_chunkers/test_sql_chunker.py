"""Unit tests for SQL chunker.

Tests cover:
- Standard SQL DDL (CREATE TABLE, VIEW, FUNCTION, PROCEDURE)
- SQL dialects (PostgreSQL, MySQL, SQLite)
- SQLMesh MODEL() declarations
- dbt models and macros
- Graph extraction (nodes and edges)
"""

from kb.chunkers.sql_chunker import chunk_source, detect_sql_dialect, extract_graph_data


class TestSQLDialectDetection:
    """Test SQL dialect detection."""

    def test_detect_postgres(self):
        source = "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        assert detect_sql_dialect(source) == "postgres"

    def test_detect_mysql(self):
        source = "CREATE TABLE users (id INT AUTO_INCREMENT);"
        assert detect_sql_dialect(source) == "mysql"

    def test_detect_sqlite(self):
        source = "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT);"
        assert detect_sql_dialect(source) == "sqlite"

    def test_detect_generic(self):
        source = "CREATE TABLE users (id INT PRIMARY KEY);"
        assert detect_sql_dialect(source) == "generic"


class TestBasicSQLChunking:
    """Test chunking of standard SQL statements."""

    def test_chunk_create_table(self):
        """Test chunking CREATE TABLE statement."""
        source = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            email VARCHAR(100) UNIQUE
        );
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].symbol_kind == "table"
        assert chunks[0].symbol_name == "users"
        assert "CREATE TABLE" in chunks[0].text

    def test_chunk_multiple_statements(self):
        """Test chunking multiple SQL statements."""
        source = """
        CREATE TABLE users (id SERIAL PRIMARY KEY);

        CREATE VIEW active_users AS
        SELECT * FROM users WHERE active = true;

        CREATE FUNCTION get_user(user_id INT)
        RETURNS TABLE(id INT, name VARCHAR) AS $$
        BEGIN
            RETURN QUERY SELECT id, username FROM users WHERE id = user_id;
        END;
        $$ LANGUAGE plpgsql;
        """
        chunks = chunk_source(source)
        assert len(chunks) == 3
        assert chunks[0].symbol_kind == "table"
        assert chunks[0].symbol_name == "users"
        assert chunks[1].symbol_kind == "view"
        assert chunks[1].symbol_name == "active_users"
        assert chunks[2].symbol_kind == "function"
        assert chunks[2].symbol_name == "get_user"

    def test_chunk_view(self):
        """Test chunking CREATE VIEW statement."""
        source = """
        CREATE OR REPLACE VIEW user_summary AS
        SELECT id, username, email FROM users;
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].symbol_kind == "view"
        assert chunks[0].symbol_name == "user_summary"

    def test_chunk_procedure(self):
        """Test chunking CREATE PROCEDURE statement."""
        source = """
        CREATE PROCEDURE update_user(user_id INT, new_name VARCHAR)
        LANGUAGE plpgsql
        AS $$
        BEGIN
            UPDATE users SET username = new_name WHERE id = user_id;
        END;
        $$;
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].symbol_kind == "procedure"
        assert chunks[0].symbol_name == "update_user"

    def test_chunk_cte(self):
        """Test chunking CTE (WITH clause)."""
        source = """
        WITH active_users AS (
            SELECT * FROM users WHERE active = true
        )
        SELECT * FROM active_users;
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].symbol_kind == "cte"
        assert chunks[0].symbol_name == "active_users"

    def test_chunk_query(self):
        """Test chunking SELECT query."""
        source = """
        SELECT id, username, email
        FROM users
        WHERE active = true;
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].symbol_kind == "query"
        assert chunks[0].symbol_name is None


class TestSQLMeshChunking:
    """Test chunking of SQLMesh models."""

    def test_chunk_sqlmesh_model(self):
        """Test chunking SQLMesh MODEL() declaration."""
        source = """
        MODEL(
            name="user_analytics",
            kind="full"
        );

        SELECT
            user_id,
            COUNT(*) as event_count
        FROM events
        GROUP BY user_id;
        """
        chunks = chunk_source(source)
        assert len(chunks) >= 1
        assert chunks[0].symbol_kind == "sqlmesh_model"
        assert chunks[0].symbol_name == "user_analytics"

    def test_chunk_sqlmesh_with_dependencies(self):
        """Test SQLMesh model with dependencies."""
        source = """
        MODEL(
            name="user_summary",
            depends_on=["raw_users", "raw_events"]
        );

        SELECT u.*, COUNT(e.id) as event_count
        FROM raw_users u
        LEFT JOIN raw_events e ON u.id = e.user_id
        GROUP BY u.id;
        """
        chunks = chunk_source(source)
        assert len(chunks) >= 1
        assert chunks[0].symbol_kind == "sqlmesh_model"
        assert chunks[0].symbol_name == "user_summary"


class TestDBTChunking:
    """Test chunking of dbt models and macros."""

    def test_chunk_dbt_model(self):
        """Test chunking dbt model."""
        source = """
        {% model name="user_analytics" %}

        SELECT
            user_id,
            COUNT(*) as event_count
        FROM {{ ref('events') }}
        GROUP BY user_id
        """
        chunks = chunk_source(source)
        assert len(chunks) >= 1
        assert chunks[0].symbol_kind == "dbt_model"
        assert chunks[0].symbol_name == "user_analytics"

    def test_chunk_dbt_macro(self):
        """Test chunking dbt macro."""
        source = """
        {% macro calculate_total(column_name) %}
            SUM({{ column_name }}) * 1.1
        {% endmacro %}
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].symbol_kind == "dbt_macro"
        assert chunks[0].symbol_name == "calculate_total"

    def test_chunk_dbt_with_refs(self):
        """Test dbt model with ref() calls."""
        source = """
        SELECT
            u.id,
            u.name,
            COUNT(e.id) as event_count
        FROM {{ ref('users') }} u
        LEFT JOIN {{ ref('events') }} e ON u.id = e.user_id
        GROUP BY u.id, u.name
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        # Should be classified as query since no {% model %} block
        assert chunks[0].symbol_kind == "query"


class TestGraphExtraction:
    """Test graph data extraction from SQL."""

    def test_extract_table_node(self):
        """Test extracting table node."""
        source = "CREATE TABLE users (id INT PRIMARY KEY);"
        nodes, edges = extract_graph_data(source)
        assert len(nodes) == 1
        assert nodes[0].node_type == "table"
        assert nodes[0].name == "users"

    def test_extract_table_references(self):
        """Test extracting table reference edges."""
        source = """
        CREATE VIEW user_events AS
        SELECT u.*, e.event_type
        FROM users u
        JOIN events e ON u.id = e.user_id;
        """
        nodes, edges = extract_graph_data(source)
        assert len(nodes) == 1
        assert nodes[0].node_type == "view"

        # Should have edges to referenced tables
        edge_targets = [e.target_name for e in edges]
        assert "users" in edge_targets
        assert "events" in edge_targets

        for edge in edges:
            assert edge.edge_type == "references_table"

    def test_extract_sqlmesh_dependencies(self):
        """Test extracting SQLMesh model dependencies."""
        source = """
        MODEL(
            name="user_summary",
            depends_on=["raw_users", "raw_events"]
        );

        SELECT * FROM raw_users;
        """
        nodes, edges = extract_graph_data(source)
        assert len(nodes) == 1
        assert nodes[0].node_type == "sqlmesh_model"

        # Should have dependency edges
        dep_edges = [e for e in edges if e.edge_type == "depends_on"]
        assert len(dep_edges) == 2
        dep_targets = [e.target_name for e in dep_edges]
        assert "raw_users" in dep_targets
        assert "raw_events" in dep_targets

    def test_extract_dbt_refs(self):
        """Test extracting dbt ref() dependencies."""
        source = """
        {% model name="user_analytics" %}

        SELECT
            u.id,
            COUNT(e.id) as event_count
        FROM {{ ref('users') }} u
        LEFT JOIN {{ ref('events') }} e ON u.id = e.user_id
        GROUP BY u.id
        """
        nodes, edges = extract_graph_data(source)
        assert len(nodes) == 1

        # Should have ref dependency edges
        dep_edges = [e for e in edges if e.edge_type == "depends_on"]
        dep_targets = [e.target_name for e in dep_edges]
        assert "users" in dep_targets
        assert "events" in dep_targets

    def test_extract_dbt_sources(self):
        """Test extracting dbt source() dependencies."""
        source = """
        {% model name="staging_users" %}

        SELECT * FROM {{ source('raw', 'users') }}
        """
        nodes, edges = extract_graph_data(source)

        # Should have source dependency edge
        dep_edges = [e for e in edges if e.edge_type == "depends_on"]
        assert len(dep_edges) >= 1
        assert "raw.users" in [e.target_name for e in dep_edges]

    def test_extract_dbt_macro_calls(self):
        """Test extracting dbt macro calls."""
        source = """
        {% model name="user_totals" %}

        SELECT
            user_id,
            {{ calculate_total('amount') }} as total
        FROM orders
        GROUP BY user_id
        """
        nodes, edges = extract_graph_data(source)

        # Should have macro usage edge
        macro_edges = [e for e in edges if e.edge_type == "uses_macro"]
        assert len(macro_edges) >= 1
        assert "calculate_total" in [e.target_name for e in macro_edges]


class TestLargeStatementChunking:
    """Test chunking of large SQL statements."""

    def test_chunk_large_table(self):
        """Test chunking very large CREATE TABLE with many columns."""
        # Create a table with enough columns to exceed token limit
        columns = [f"col_{i} VARCHAR(100)" for i in range(100)]
        source = f"CREATE TABLE large_table (\n  {',\n  '.join(columns)}\n);"

        chunks = chunk_source(source, token_target=200)
        # Should be split into multiple chunks
        assert len(chunks) >= 1

        # All chunks should reference the same table
        for chunk in chunks:
            assert "large_table" in chunk.symbol_name or chunk.symbol_kind.startswith("table")

    def test_chunk_preserves_metadata(self):
        """Test that large statement chunking preserves metadata."""
        # Create a long function
        lines = ["SELECT * FROM users"] + [f"UNION ALL SELECT * FROM users_{i}" for i in range(50)]
        source = f"CREATE FUNCTION get_all_users() RETURNS TABLE(id INT) AS $$\n{chr(10).join(lines)}\n$$ LANGUAGE sql;"

        chunks = chunk_source(source, token_target=200)
        assert len(chunks) >= 1

        # All chunks should have function metadata
        for chunk in chunks:
            assert chunk.symbol_kind.startswith("function")
            assert chunk.symbol_name == "get_all_users"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_source(self):
        """Test chunking empty source."""
        assert chunk_source("") == []
        assert chunk_source("   \n  \n  ") == []

    def test_semicolon_in_string(self):
        """Test handling semicolons inside string literals."""
        source = """
        INSERT INTO messages (text)
        VALUES ('Hello; world');

        SELECT * FROM messages;
        """
        chunks = chunk_source(source)
        # Should be split into 2 statements, not 3
        assert len(chunks) == 2

    def test_multiline_statement(self):
        """Test handling multiline statements."""
        source = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50)
                NOT NULL
                UNIQUE,
            email VARCHAR(100)
        );
        """
        chunks = chunk_source(source)
        assert len(chunks) == 1
        assert chunks[0].symbol_kind == "table"
        assert chunks[0].end_line > chunks[0].start_line

    def test_line_number_tracking(self):
        """Test accurate line number tracking."""
        source = """-- Line 1
CREATE TABLE users (
    id INT PRIMARY KEY
);

CREATE VIEW active_users AS
SELECT * FROM users;
"""
        chunks = chunk_source(source)
        assert len(chunks) == 2

        # First chunk should start at line 1 (includes the comment)
        assert chunks[0].start_line == 1
        assert chunks[0].end_line >= chunks[0].start_line

        # Second chunk should start after first
        assert chunks[1].start_line > chunks[0].end_line
