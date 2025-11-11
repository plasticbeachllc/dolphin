# SQL and Svelte Chunker Implementation Plan

## Executive Summary

This document outlines the implementation of chunkers for **SQL** and **Svelte** files as a **prerequisite** for the code graph enhancement. These chunkers will enable the graph system to track relationships between:

- **SQL**: Stored procedures, views, triggers, table references, and function calls
- **Svelte**: Components, reactive statements, imports, and component usage

## Rationale

Before implementing the code graph (which tracks calls, implementations, inheritance, etc.), we need to ensure that SQL and Svelte files are properly chunked and indexed. This will allow:

1. **SQL**: Track which code calls which stored procedures/functions, which queries reference which tables
2. **SQLMesh & dbt**: Track model dependencies, macro usage, and transformations
3. **Svelte**: Track component hierarchies, prop flow, and event handlers across components
4. **Cross-language relationships**: Track how Python/TypeScript code interacts with SQL databases and Svelte components

## 1. SQL Chunker Implementation

### Scope

**Supported SQL Dialects** (in order of priority):
1. PostgreSQL (most common in modern apps)
2. MySQL/MariaDB
3. SQLite
4. Generic SQL (fallback)

**Data Transformation Frameworks**:
5. **SQLMesh** - SQL-based data transformations
6. **dbt (Data Build Tool)** - SQL modeling and transformations

**Entity Types to Extract**:
- Tables (CREATE TABLE)
- Views (CREATE VIEW)
- Stored procedures/functions
- Triggers
- Indexes
- Queries (SELECT/INSERT/UPDATE/DELETE)
- CTEs (Common Table Expressions)
- **SQLMesh models** (MODEL declarations)
- **dbt models** ({% model %} blocks)
- **dbt macros** ({% macro %} definitions)
- **Jinja templates** (in dbt SQL)

### Architecture

**Option 1: Tree-Sitter SQL Parser** (Recommended)
- Use `tree-sitter-sql` or dialect-specific parsers
- Consistent with existing Python/TypeScript chunkers
- Accurate AST-based extraction

**Option 2: Regex-Based Parser**
- Simpler implementation
- Less accurate (can miss complex cases)
- Good enough for basic chunking

**Recommendation**: Start with Tree-Sitter for PostgreSQL, add other dialects as needed

### Implementation

#### File Structure

```
kb/chunkers/
  sql_chunker.py          # Main SQL chunker
  sql_parser.py           # Tree-sitter wrapper
  sql_dialects.py         # Dialect detection
```

#### SQL Chunker (`kb/chunkers/sql_chunker.py`)

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
from tree_sitter import Language, Parser

from .token_utils import get_tokenizer, count_tokens
from .types import Chunk

# SQL dialect detection
SQL_DIALECTS = {
    'postgres': ['SERIAL', 'BIGSERIAL', 'RETURNING', '::'],
    'mysql': ['AUTO_INCREMENT', 'TINYINT', 'MEDIUMINT'],
    'sqlite': ['AUTOINCREMENT', 'WITHOUT ROWID'],
}

def detect_sql_dialect(source: str) -> str:
    """Detect SQL dialect from source code."""
    source_upper = source.upper()
    
    for dialect, keywords in SQL_DIALECTS.items():
        if any(keyword in source_upper for keyword in keywords):
            return dialect
    
    return 'generic'

def chunk_source(
    source: str,
    *,
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> List[Chunk]:
    """Chunk SQL source into logical units.
    
    Chunking strategy:
    - Each CREATE TABLE/VIEW/FUNCTION/PROCEDURE as separate chunk
    - Large queries broken into manageable pieces
    - CTEs chunked as units
    """
    
    # Detect dialect
    dialect = detect_sql_dialect(source)
    
    chunks = []
    tok = get_tokenizer(model)
    
    # Extract all CREATE statements (tables, views, functions, procedures)
    create_pattern = r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?(?:TABLE|VIEW|FUNCTION|PROCEDURE|TRIGGER|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+\.?\w*)'
    
    # Split source into statements (basic semicolon splitting)
    statements = _split_sql_statements(source)
    
    current_line = 1
    for statement in statements:
        if not statement.strip():
            current_line += statement.count('\n')
            continue
        
        statement_type, entity_name = _classify_statement(statement)
        
        # Calculate line numbers
        start_line = current_line
        end_line = current_line + statement.count('\n')
        
        # Extract chunk
        chunk_text = statement.strip()
        token_count = count_tokens(chunk_text, tok)
        
        # If too large, break into smaller pieces
        if token_count > token_target * 1.5:
            sub_chunks = _chunk_large_statement(
                chunk_text, 
                start_line, 
                model=model, 
                token_target=token_target
            )
            chunks.extend(sub_chunks)
        else:
            chunks.append(Chunk(
                text=chunk_text,
                start_line=start_line,
                end_line=end_line,
                token_count=token_count,
                symbol_kind=statement_type,
                symbol_name=entity_name,
                symbol_path=entity_name
            ))
        
        current_line = end_line + 1
    
    return chunks

def _split_sql_statements(source: str) -> List[str]:
    """Split SQL source into individual statements.
    
    Handles:
    - Semicolon-terminated statements
    - Statements with string literals containing semicolons
    - Multi-line statements
    """
    statements = []
    current = []
    in_string = False
    string_char = None
    
    lines = source.split('\n')
    for line in lines:
        # Track string literals to avoid splitting on semicolons inside strings
        for char in line:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
        
        current.append(line)
        
        # Check for statement terminator (semicolon outside strings)
        if ';' in line and not in_string:
            statements.append('\n'.join(current))
            current = []
    
    # Add any remaining content
    if current:
        statements.append('\n'.join(current))
    
    return statements

def _classify_statement(statement: str) -> tuple[str, Optional[str]]:
    """Classify SQL statement and extract entity name.
    
    Returns:
        (statement_type, entity_name)
    """
    statement_upper = statement.upper().strip()
    
    # CREATE TABLE/VIEW/FUNCTION/PROCEDURE/TRIGGER
    create_match = re.search(
        r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?'
        r'(TABLE|VIEW|FUNCTION|PROCEDURE|TRIGGER|INDEX)\s+'
        r'(?:IF\s+NOT\s+EXISTS\s+)?'
        r'([\w.]+)',
        statement_upper
    )
    if create_match:
        entity_type = create_match.group(1).lower()
        entity_name = create_match.group(2).lower()
        return entity_type, entity_name
    
    # SELECT/INSERT/UPDATE/DELETE queries
    for query_type in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']:
        if statement_upper.startswith(query_type):
            return 'query', None
    
    # WITH (CTE)
    if statement_upper.startswith('WITH'):
        return 'cte', None
    
    return 'statement', None

def _chunk_large_statement(
    statement: str, 
    start_line: int, 
    model: str, 
    token_target: int
) -> List[Chunk]:
    """Break large SQL statement into smaller chunks."""
    # Simple line-based chunking for now
    # TODO: Implement smarter chunking based on SQL structure
    
    lines = statement.split('\n')
    chunks = []
    current_chunk = []
    current_line = start_line
    tok = get_tokenizer(model)
    
    for i, line in enumerate(lines):
        current_chunk.append(line)
        chunk_text = '\n'.join(current_chunk)
        
        if count_tokens(chunk_text, tok) > token_target:
            if len(current_chunk) > 1:
                # Save previous chunk
                prev_text = '\n'.join(current_chunk[:-1])
                chunks.append(Chunk(
                    text=prev_text,
                    start_line=current_line,
                    end_line=current_line + len(current_chunk) - 2,
                    token_count=count_tokens(prev_text, tok),
                    symbol_kind='statement_part',
                    symbol_name=None,
                    symbol_path=None
                ))
                current_line += len(current_chunk) - 1
                current_chunk = [line]
    
    # Add final chunk
    if current_chunk:
        chunk_text = '\n'.join(current_chunk)
        chunks.append(Chunk(
            text=chunk_text,
            start_line=current_line,
            end_line=current_line + len(current_chunk) - 1,
            token_count=count_tokens(chunk_text, tok),
            symbol_kind='statement_part',
            symbol_name=None,
            symbol_path=None
        ))
    
    return chunks
```

### Graph Extraction for SQL

#### Entities (Nodes)
```python
# SQL entities that become graph nodes
- Table definitions → node_type='table'
- View definitions → node_type='view'
- Functions/Procedures → node_type='function'
- Triggers → node_type='trigger'
```

#### Relationships (Edges)
```python
# SQL relationships that become graph edges

1. Table References (in queries)
   - edge_type='references_table'
   - FROM clause, JOIN clauses
   
2. Function Calls
   - edge_type='calls'
   - User-defined functions called in queries
   
3. View Dependencies
   - edge_type='depends_on'
   - Tables/views referenced in view definition
   
4. Trigger Associations
   - edge_type='triggers_on'
   - Table that trigger is attached to
   
5. Foreign Key Relationships
   - edge_type='foreign_key'
   - References between tables
```

#### Example Graph Extraction

```python
def extract_sql_graph(source: str, path: str, repo: str) -> tuple[List[GraphNode], List[GraphEdge]]:
    """Extract graph nodes and edges from SQL source."""
    
    nodes = []
    edges = []
    
    statements = _split_sql_statements(source)
    
    for statement in statements:
        stmt_type, entity_name = _classify_statement(statement)
        
        if stmt_type in ['table', 'view', 'function', 'procedure']:
            # Create node
            node_id = f"{repo}:{path}:{stmt_type}:{entity_name}"
            nodes.append(GraphNode(
                id=node_id,
                node_type=stmt_type,
                name=entity_name,
                qualified_name=f"{repo}.{entity_name}",
                path=path,
                start_line=1,  # TODO: track actual line
                end_line=1
            ))
            
            # Extract table references
            if stmt_type in ['view', 'function']:
                referenced_tables = _extract_table_references(statement)
                for table in referenced_tables:
                    edges.append(GraphEdge(
                        source_node_id=node_id,
                        target_node_id=f"{repo}:{path}:table:{table}",
                        edge_type='references_table',
                        path=path,
                        line_number=1
                    ))
    
    return nodes, edges

def _extract_table_references(sql: str) -> List[str]:
    """Extract table names from SQL statement."""
    # Match FROM and JOIN clauses
    pattern = r'(?:FROM|JOIN)\s+([\w.]+)'
    matches = re.findall(pattern, sql, re.IGNORECASE)
    return [m.lower() for m in matches]
```

## 2. Svelte Chunker Implementation

### Scope

**Svelte-Specific Features**:
- Single File Components (.svelte)
- `<script>`, `<style>`, `<template>` sections
- Reactive declarations ($:)
- Component props (export let)
- Component imports and usage
- Stores and reactive statements

### Architecture

**Parser Strategy**:
1. **HTML Parser**: Parse Svelte template structure
2. **JavaScript Parser**: Use existing ts_chunker for `<script>` sections
3. **CSS Parser**: Basic extraction for `<style>` sections

### Implementation

#### File Structure

```
kb/chunkers/
  svelte_chunker.py       # Main Svelte chunker
  svelte_parser.py        # Svelte-specific parsing
```

#### Svelte Chunker (`kb/chunkers/svelte_chunker.py`)

```python
from __future__ import annotations

import re
from typing import List
from html.parser import HTMLParser

from .token_utils import get_tokenizer, count_tokens
from .types import Chunk
from .ts_chunker import chunk_source as chunk_typescript

class SvelteComponentParser(HTMLParser):
    """Parse Svelte component structure."""
    
    def __init__(self):
        super().__init__()
        self.sections = {
            'script': [],
            'style': [],
            'template': []
        }
        self.current_section = None
        self.current_data = []
    
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.current_section = tag
            self.current_data = []
    
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.current_section == tag:
            self.sections[tag].append(''.join(self.current_data))
            self.current_section = None
    
    def handle_data(self, data):
        if self.current_section:
            self.current_data.append(data)
        else:
            # Template content
            self.sections['template'].append(data)

def chunk_source(
    source: str,
    *,
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> List[Chunk]:
    """Chunk Svelte component into logical units.
    
    Strategy:
    - Extract <script>, <style>, <template> sections
    - Chunk <script> using TypeScript chunker
    - Chunk template by component structure
    - Keep <style> as single chunk (usually small)
    """
    
    chunks = []
    tok = get_tokenizer(model)
    
    # Parse component structure
    parser = SvelteComponentParser()
    try:
        parser.feed(source)
    except Exception as e:
        # Fallback: treat as plain text
        return _fallback_chunking(source, model, token_target)
    
    current_line = 1
    
    # Chunk <script> section(s)
    for script_content in parser.sections['script']:
        if not script_content.strip():
            continue
        
        # Use TypeScript chunker for script content
        script_chunks = chunk_typescript(
            script_content,
            model=model,
            token_target=token_target,
            overlap_pct=overlap_pct
        )
        
        # Adjust line numbers
        for chunk in script_chunks:
            chunks.append(Chunk(
                text=chunk.text,
                start_line=current_line + chunk.start_line - 1,
                end_line=current_line + chunk.end_line - 1,
                token_count=chunk.token_count,
                symbol_kind=f"svelte_script_{chunk.symbol_kind}" if chunk.symbol_kind else "svelte_script",
                symbol_name=chunk.symbol_name,
                symbol_path=chunk.symbol_path
            ))
        
        current_line += script_content.count('\n') + 1
    
    # Chunk <style> section (usually small, keep as single chunk)
    for style_content in parser.sections['style']:
        if not style_content.strip():
            continue
        
        token_count = count_tokens(style_content, tok)
        chunks.append(Chunk(
            text=style_content,
            start_line=current_line,
            end_line=current_line + style_content.count('\n'),
            token_count=token_count,
            symbol_kind='svelte_style',
            symbol_name=None,
            symbol_path=None
        ))
        current_line += style_content.count('\n') + 1
    
    # Chunk template section
    template = '\n'.join(parser.sections['template'])
    if template.strip():
        # Extract component tags
        component_chunks = _chunk_template(template, current_line, tok, token_target)
        chunks.extend(component_chunks)
    
    return chunks if chunks else _fallback_chunking(source, model, token_target)

def _chunk_template(
    template: str,
    start_line: int,
    tokenizer,
    token_target: int
) -> List[Chunk]:
    """Chunk Svelte template by component usage and control flow."""
    
    chunks = []
    
    # Extract component usages
    component_pattern = r'<([A-Z]\w+)[^>]*>'
    components = re.findall(component_pattern, template)
    
    # If template is small, keep as single chunk
    token_count = count_tokens(template, tokenizer)
    if token_count <= token_target:
        chunks.append(Chunk(
            text=template,
            start_line=start_line,
            end_line=start_line + template.count('\n'),
            token_count=token_count,
            symbol_kind='svelte_template',
            symbol_name=None,
            symbol_path=None
        ))
    else:
        # Split into smaller chunks (simple line-based for now)
        lines = template.split('\n')
        chunk_lines = []
        chunk_start = start_line
        
        for i, line in enumerate(lines):
            chunk_lines.append(line)
            chunk_text = '\n'.join(chunk_lines)
            
            if count_tokens(chunk_text, tokenizer) > token_target:
                if len(chunk_lines) > 1:
                    prev_text = '\n'.join(chunk_lines[:-1])
                    chunks.append(Chunk(
                        text=prev_text,
                        start_line=chunk_start,
                        end_line=chunk_start + len(chunk_lines) - 2,
                        token_count=count_tokens(prev_text, tokenizer),
                        symbol_kind='svelte_template',
                        symbol_name=None,
                        symbol_path=None
                    ))
                    chunk_start += len(chunk_lines) - 1
                    chunk_lines = [line]
        
        # Add final chunk
        if chunk_lines:
            chunk_text = '\n'.join(chunk_lines)
            chunks.append(Chunk(
                text=chunk_text,
                start_line=chunk_start,
                end_line=chunk_start + len(chunk_lines) - 1,
                token_count=count_tokens(chunk_text, tokenizer),
                symbol_kind='svelte_template',
                symbol_name=None,
                symbol_path=None
            ))
    
    return chunks

def _fallback_chunking(source: str, model: str, token_target: int) -> List[Chunk]:
    """Fallback: simple token-based chunking."""
    from .fallback_chunker import chunk_source as fallback_chunk
    return fallback_chunk(source, model=model, token_target=token_target)
```

### Graph Extraction for Svelte

#### Entities (Nodes)
```python
# Svelte entities that become graph nodes
- Component file → node_type='svelte_component'
- Exported functions/variables → node_type='function'/'variable'
- Stores → node_type='store'
```

#### Relationships (Edges)
```python
# Svelte relationships that become graph edges

1. Component Usage
   - edge_type='uses_component'
   - <MyComponent> tags in template
   
2. Imports
   - edge_type='imports'
   - import statements in <script>
   
3. Store Subscriptions
   - edge_type='subscribes_to'
   - $store references
   
4. Props
   - edge_type='accepts_prop'
   - export let declarations
   
5. Events
   - edge_type='dispatches_event'
   - createEventDispatcher calls
```

## Registration and Integration

### Update Chunker Registry

```python
# kb/chunkers/registry.py

LANGUAGE_CHUNKERS = {
    'python': 'kb.chunkers.py_chunker',
    'typescript': 'kb.chunkers.ts_chunker',
    'javascript': 'kb.chunkers.ts_chunker',
    'markdown': 'kb.chunkers.md_chunker',
    'sql': 'kb.chunkers.sql_chunker',        # NEW
    'svelte': 'kb.chunkers.svelte_chunker',  # NEW
}

EXTENSION_TO_LANGUAGE = {
    '.py': 'python',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.md': 'markdown',
    '.sql': 'sql',              # NEW
    '.svelte': 'svelte',        # NEW
}
```

## Implementation Timeline

### Phase 0: Prerequisites (1 week)

**Before starting code graph implementation**

**Week 1: SQL & Svelte Chunkers**
- [ ] Implement basic SQL chunker (3 days)
  - Statement splitting
  - Entity extraction
  - Basic graph support
- [ ] Implement Svelte chunker (2 days)
  - Section parsing
  - Component extraction
  - Integration with ts_chunker
- [ ] Testing & validation (2 days)
  - Unit tests
  - Integration tests
  - Sample file testing

**Deliverables**:
- `kb/chunkers/sql_chunker.py`
- `kb/chunkers/svelte_chunker.py`
- Updated registry
- Test suite

## Testing Strategy

### SQL Chunker Tests

```python
# tests/unit/test_chunkers/test_sql_chunker.py

def test_chunk_create_table():
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
    assert chunks[0].symbol_kind == 'table'
    assert chunks[0].symbol_name == 'users'

def test_chunk_multiple_statements():
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
    assert chunks[0].symbol_kind == 'table'
    assert chunks[1].symbol_kind == 'view'
    assert chunks[2].symbol_kind == 'function'
```

### Svelte Chunker Tests

```python
# tests/unit/test_chunkers/test_svelte_chunker.py

def test_chunk_svelte_component():
    """Test chunking basic Svelte component."""
    source = """
    <script>
        export let name;
        let count = 0;
        
        function increment() {
            count += 1;
        }
    </script>
    
    <button on:click={increment}>
        Clicks: {count}
    </button>
    
    <style>
        button { color: blue; }
    </style>
    """
    chunks = chunk_source(source)
    assert len(chunks) >= 2  # script + template (+ maybe style)
    
    # Check for script chunks
    script_chunks = [c for c in chunks if 'script' in c.symbol_kind]
    assert len(script_chunks) > 0
```

## Success Criteria

### SQL Chunker
- ✅ Correctly identifies CREATE TABLE/VIEW/FUNCTION/PROCEDURE
- ✅ Extracts entity names
- ✅ Handles multiple statements
- ✅ Supports PostgreSQL, MySQL, SQLite dialects
- ✅ Provides graph node/edge data

### Svelte Chunker
- ✅ Parses `<script>`, `<style>`, `<template>` sections
- ✅ Chunks JavaScript in `<script>` using ts_chunker
- ✅ Identifies component usage in templates
- ✅ Extracts props and stores
- ✅ Provides graph node/edge data

## Next Steps

1. ⏳ Implement SQL chunker
2. ⏳ Implement Svelte chunker
3. ⏳ Update chunker registry
4. ⏳ Add comprehensive tests
5. ⏳ Test on real SQL/Svelte files
6. ✅ **Proceed with code graph implementation** (from original plan)

## References

- SQL Tree-Sitter: https://github.com/tree-sitter/tree-sitter-sql
- Svelte Language Tools: https://github.com/sveltejs/language-tools
- Svelte Compiler: https://github.com/sveltejs/svelte