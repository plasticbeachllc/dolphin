# Golden Scenarios Specification

Golden scenarios are curated test cases that define expected retrieval behavior. They enable systematic evaluation of retrieval quality and regression prevention.

## Table of Contents

- [Overview](#overview)
- [Scenario Format](#scenario-format)
- [Scenario Types](#scenario-types)
- [Creating Scenarios](#creating-scenarios)
- [Organizing Scenarios](#organizing-scenarios)
- [Evaluation Process](#evaluation-process)
- [Best Practices](#best-practices)
- [Examples](#examples)

---

## Overview

### What are Golden Scenarios?

Golden scenarios are **structured test cases** that specify:
1. A query (natural language or code pattern)
2. Expected results (files, symbols, or chunks)
3. Relevance judgments and ranking constraints
4. Metadata about difficulty and category

### Why Golden Scenarios?

**Regression detection**: Catch when changes break existing behavior
**Objective measurement**: Compute MRR, P@K, R@K from expected vs. actual results
**Development guidance**: Document expected behavior as executable tests
**Quality gates**: Block PRs that degrade retrieval quality

### Scope

Golden scenarios cover:
- Code search (find functions, classes, definitions)
- Semantic search (conceptual queries)
- Hybrid search (combining exact matches and semantics)
- Cross-file navigation (find usages, dependencies)

---

## Scenario Format

### JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "query", "expected_results"],
  "properties": {
    "id": {
      "type": "string",
      "description": "Unique identifier (kebab-case)"
    },
    "query": {
      "type": "string",
      "description": "The search query (natural language or code pattern)"
    },
    "repo": {
      "type": "string",
      "description": "Repository name or path (optional, defaults to dolphin)"
    },
    "expected_results": {
      "type": "array",
      "description": "List of expected results in priority order",
      "items": {
        "type": "object",
        "required": ["file"],
        "properties": {
          "file": {
            "type": "string",
            "description": "Relative file path from repo root"
          },
          "symbol": {
            "type": "string",
            "description": "Function/class name (optional)"
          },
          "line_range": {
            "type": "object",
            "properties": {
              "start": {"type": "integer"},
              "end": {"type": "integer"}
            }
          },
          "rank": {
            "type": "integer",
            "description": "Expected rank (1-indexed, optional)"
          },
          "relevance": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Relevance score 0-1 (optional, default 1.0)"
          }
        }
      }
    },
    "metadata": {
      "type": "object",
      "properties": {
        "category": {
          "type": "string",
          "enum": ["code-search", "semantic-search", "hybrid-search", "navigation"]
        },
        "difficulty": {
          "type": "string",
          "enum": ["easy", "medium", "hard"]
        },
        "description": {
          "type": "string"
        },
        "tags": {
          "type": "array",
          "items": {"type": "string"}
        }
      }
    }
  }
}
```

### Minimal Example

```json
{
  "id": "find-lancedb-store",
  "query": "LanceDBStore class",
  "expected_results": [
    {
      "file": "kb/store/lancedb_store.py",
      "symbol": "LanceDBStore"
    }
  ]
}
```

### Complete Example

```json
{
  "id": "parse-markdown-tables",
  "query": "function to parse markdown tables",
  "repo": "dolphin",
  "expected_results": [
    {
      "file": "kb/parsers/markdown.py",
      "symbol": "parse_table",
      "rank": 1,
      "relevance": 1.0
    },
    {
      "file": "kb/parsers/markdown.py",
      "symbol": "extract_table_rows",
      "rank": 2,
      "relevance": 0.8
    },
    {
      "file": "tests/unit/parsers/test_markdown.py",
      "symbol": "test_parse_table",
      "rank": 3,
      "relevance": 0.6
    }
  ],
  "metadata": {
    "category": "code-search",
    "difficulty": "medium",
    "description": "Natural language query for specific functionality",
    "tags": ["parsing", "markdown", "tables"]
  }
}
```

---

## Scenario Types

### 1. Code Search

**Purpose**: Find specific code elements by name or description.

**Examples**:
- "find the LanceDBStore class"
- "search function that computes embeddings"
- "locate error handling in the API"

**Expected results**: Specific functions, classes, or code blocks.

**Relevance criteria**:
- **Rank 1**: Exact match (definition)
- **Rank 2-3**: Related implementations
- **Rank 4+**: Tests or documentation

### 2. Semantic Search

**Purpose**: Find code by concept or behavior, not exact names.

**Examples**:
- "how does authentication work?"
- "code that handles rate limiting"
- "find examples of retry logic"

**Expected results**: Code implementing the concept, even with different names.

**Relevance criteria**:
- **1.0**: Direct implementation
- **0.8**: Related or partial implementation
- **0.6**: Examples or tests
- **0.4**: Documentation or comments

### 3. Hybrid Search

**Purpose**: Combine exact matching with semantic understanding.

**Examples**:
- "FastAPI endpoint for searching"
- "pytest fixtures for database setup"
- "React component that renders diffs"

**Expected results**: Mix of exact matches and conceptually related code.

**Characteristics**:
- Includes specific technical terms (FastAPI, pytest, React)
- Also includes behavioral context (searching, database setup, renders diffs)

### 4. Navigation

**Purpose**: Cross-file relationships like usages, imports, or dependencies.

**Examples**:
- "find all usages of LanceDBStore"
- "where is ANNParams imported?"
- "functions that call benchmark_configuration"

**Expected results**: Call sites, import statements, or references.

**Note**: May require code graph or FTS in addition to vector search.

---

## Creating Scenarios

### Step 1: Identify Test Cases

Sources of good scenarios:
- **User queries**: Real searches from usage logs
- **Bug reports**: Queries that returned poor results
- **Feature requirements**: Expected behavior for new features
- **Edge cases**: Difficult queries (ambiguous, rare terms, etc.)

### Step 2: Execute Query

Run the query against your system:
```bash
# Via API
curl -X POST http://localhost:7777/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "function to parse markdown tables", "top_k": 10}'

# Via CLI
dolphin search "function to parse markdown tables" --top-k 10
```

### Step 3: Curate Expected Results

Review actual results and determine:
1. Which results are **relevant**?
2. What is the **ideal ranking**?
3. Are there **missing results** that should appear?

**Guidelines**:
- Include 3-5 expected results (top-k coverage)
- Assign ranks to enforce ordering constraints
- Use relevance scores (0-1) for partial matches

### Step 4: Add Metadata

Categorize the scenario:
- **Category**: code-search, semantic-search, hybrid-search, navigation
- **Difficulty**: easy (exact match), medium (semantic), hard (ambiguous)
- **Tags**: Relevant technology keywords
- **Description**: Why this scenario matters

### Step 5: Validate

Test the scenario:
```bash
python scripts/eval_retrieval.py \
  --scenario golden-scenarios/code-search/parse-markdown-tables.json \
  --verbose
```

Ensure:
- Expected results are found (recall)
- Ranking is reasonable (MRR, P@K)
- Query is realistic and repeatable

---

## Organizing Scenarios

### Directory Structure

```
golden-scenarios/
├── README.md                    # Overview and instructions
├── code-search/                 # Code search scenarios
│   ├── exact-match/            # Simple name-based queries
│   │   ├── class-lookup.json
│   │   └── function-lookup.json
│   ├── description-based/      # Natural language descriptions
│   │   ├── parse-markdown.json
│   │   └── error-handling.json
│   └── cross-language/         # Multi-language queries
│       └── typescript-python.json
├── semantic-search/            # Conceptual queries
│   ├── architecture/           # High-level concepts
│   │   ├── authentication.json
│   │   └── caching.json
│   ├── patterns/               # Design patterns
│   │   ├── retry-logic.json
│   │   └── factory-pattern.json
│   └── edge-cases/             # Difficult semantic queries
│       └── ambiguous-terms.json
├── hybrid-search/              # Combined queries
│   ├── framework-specific/     # FastAPI, pytest, React, etc.
│   │   ├── fastapi-endpoints.json
│   │   └── pytest-fixtures.json
│   └── behavioral/             # Specific behavior + tech
│       └── rate-limiting.json
└── navigation/                 # Cross-file relationships
    ├── usages/                 # Find usages
    │   └── lancedb-usages.json
    ├── imports/                # Import tracking
    │   └── ann-params-imports.json
    └── dependencies/           # Dependency chains
        └── embeddings-deps.json
```

### Naming Conventions

**File names**: `{query-slug}.json`
- Use kebab-case
- Descriptive but concise
- Example: `parse-markdown-tables.json`

**Scenario IDs**: `{category}-{description}`
- Match file name pattern
- Globally unique
- Example: `code-search-parse-markdown-tables`

### Bundling Scenarios

For related scenarios, use JSON arrays:

```json
[
  {
    "id": "lancedb-class",
    "query": "LanceDBStore class",
    "expected_results": [...]
  },
  {
    "id": "lancedb-query-method",
    "query": "LanceDBStore query method",
    "expected_results": [...]
  }
]
```

---

## Evaluation Process

### Running Evaluation

```bash
# Single scenario
python scripts/eval_retrieval.py \
  --scenario golden-scenarios/code-search/parse-markdown.json

# Directory of scenarios
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/code-search/

# All scenarios
python scripts/eval_retrieval.py \
  --scenarios golden-scenarios/ \
  --output results/eval.json
```

### Scoring

For each scenario:
1. **Execute query** against the system
2. **Match results** to expected results (by file + symbol)
3. **Compute metrics**:
   - MRR (position of first expected result)
   - P@K (fraction of top-K that are expected)
   - R@K (fraction of expected results in top-K)

### Pass/Fail Criteria

**Per-scenario thresholds**:
- **Easy scenarios**: MRR ≥ 0.90, P@5 ≥ 0.80
- **Medium scenarios**: MRR ≥ 0.80, P@5 ≥ 0.70
- **Hard scenarios**: MRR ≥ 0.70, P@5 ≥ 0.60

**Overall thresholds** (all scenarios):
- **MRR** ≥ 0.85
- **P@5** ≥ 0.75
- **R@10** ≥ 0.90

### Output Format

```json
{
  "summary": {
    "total_scenarios": 50,
    "passed": 47,
    "failed": 3,
    "metrics": {
      "mrr": 0.872,
      "p@5": 0.784,
      "p@10": 0.691,
      "r@10": 0.923
    }
  },
  "scenarios": [
    {
      "id": "parse-markdown-tables",
      "query": "function to parse markdown tables",
      "status": "passed",
      "metrics": {
        "mrr": 1.0,
        "p@5": 0.8,
        "r@10": 1.0
      },
      "results": [
        {"file": "kb/parsers/markdown.py", "symbol": "parse_table", "rank": 1, "expected": true},
        {"file": "kb/parsers/markdown.py", "symbol": "extract_table_rows", "rank": 2, "expected": true},
        ...
      ]
    },
    ...
  ],
  "failures": [
    {
      "id": "ambiguous-query",
      "reason": "MRR 0.50 below threshold 0.70",
      "details": "Expected result at rank 2 instead of 1"
    }
  ]
}
```

---

## Best Practices

### Scenario Quality

**Do**:
- Use realistic, user-like queries
- Cover diverse query types and difficulties
- Include both common and edge cases
- Document why each scenario matters
- Keep scenarios independent (no ordering dependencies)

**Don't**:
- Create overly specific or brittle scenarios
- Expect perfect ranking for ambiguous queries
- Include implementation details in queries
- Duplicate scenarios unnecessarily

### Maintenance

**Regular review**: Update scenarios when code changes
**Version control**: Track scenario changes alongside code
**Prune obsolete**: Remove scenarios for deleted functionality
**Expand coverage**: Add scenarios for new features

### Coverage Goals

Target **50+ scenarios** with distribution:
- **40%** code search (exact and description-based)
- **30%** semantic search
- **20%** hybrid search
- **10%** navigation

Difficulty distribution:
- **50%** easy (baseline correctness)
- **35%** medium (realistic complexity)
- **15%** hard (stretch goals)

---

## Examples

### Example 1: Exact Match (Easy)

```json
{
  "id": "exact-lancedb-store",
  "query": "LanceDBStore",
  "expected_results": [
    {
      "file": "kb/store/lancedb_store.py",
      "symbol": "LanceDBStore",
      "rank": 1
    }
  ],
  "metadata": {
    "category": "code-search",
    "difficulty": "easy",
    "description": "Exact class name lookup"
  }
}
```

### Example 2: Description-Based (Medium)

```json
{
  "id": "embedding-generation",
  "query": "code that generates embeddings from text",
  "expected_results": [
    {
      "file": "kb/embeddings/provider.py",
      "symbol": "embed_texts",
      "rank": 1,
      "relevance": 1.0
    },
    {
      "file": "kb/embeddings/provider.py",
      "symbol": "EmbeddingProvider",
      "rank": 2,
      "relevance": 0.9
    },
    {
      "file": "kb/embeddings/batch.py",
      "symbol": "batch_embed",
      "rank": 3,
      "relevance": 0.7
    }
  ],
  "metadata": {
    "category": "semantic-search",
    "difficulty": "medium",
    "description": "Natural language query for functionality",
    "tags": ["embeddings", "text-processing"]
  }
}
```

### Example 3: Ambiguous Query (Hard)

```json
{
  "id": "store-implementation",
  "query": "store",
  "expected_results": [
    {
      "file": "kb/store/lancedb_store.py",
      "symbol": "LanceDBStore",
      "relevance": 0.9
    },
    {
      "file": "kb/store/sqlite_meta.py",
      "symbol": "SQLiteMetadataStore",
      "relevance": 0.9
    },
    {
      "file": "kb/store/base.py",
      "symbol": "VectorStore",
      "relevance": 0.8
    }
  ],
  "metadata": {
    "category": "semantic-search",
    "difficulty": "hard",
    "description": "Ambiguous term - should find all store implementations",
    "tags": ["ambiguous", "multi-result"]
  }
}
```

### Example 4: Cross-File Navigation

```json
{
  "id": "ann-params-usages",
  "query": "find all usages of ANNParams",
  "expected_results": [
    {
      "file": "kb/retrieval/ann_tuning.py",
      "symbol": "ANNParams",
      "rank": 1,
      "relevance": 1.0
    },
    {
      "file": "scripts/benchmark_ann.py",
      "symbol": "benchmark_configuration",
      "relevance": 0.8
    },
    {
      "file": "kb/store/lancedb_store.py",
      "symbol": "query",
      "relevance": 0.8
    }
  ],
  "metadata": {
    "category": "navigation",
    "difficulty": "medium",
    "description": "Find all files that use ANNParams",
    "tags": ["cross-file", "usages"]
  }
}
```

---

## Tools and Automation

### Scenario Generator

```bash
# Generate scenario from query
python scripts/generate_scenario.py \
  --query "function to parse markdown tables" \
  --interactive  # Prompts for curation
```

### Scenario Validator

```bash
# Validate scenario format
python scripts/validate_scenarios.py golden-scenarios/

# Check for duplicates
python scripts/validate_scenarios.py --check-duplicates
```

### Coverage Analyzer

```bash
# Analyze scenario coverage
python scripts/analyze_coverage.py golden-scenarios/

# Output:
# - Category distribution
# - Difficulty distribution
# - File coverage (which files are tested)
# - Symbol coverage (which functions/classes)
```

---

## Summary

Golden scenarios are:
1. **Structured test cases** with queries and expected results
2. **Evaluation foundation** for computing MRR, P@K, R@K
3. **Regression prevention** to catch quality degradation
4. **Development guidance** documenting expected behavior

**Start small**: Begin with 10-20 scenarios covering core use cases.
**Iterate**: Add scenarios when bugs are found or features are added.
**Maintain**: Review and update scenarios as the codebase evolves.

**Next**: See [Retrieval Evaluation](./retrieval-evaluation.md) for running evaluations.
