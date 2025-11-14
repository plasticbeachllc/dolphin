# Golden Scenarios - Flask Test Repository

Custom golden scenarios for symbol-level search testing using Flask 2.3.0 as the test corpus.

## Test Repository

**Repo**: `pallets/flask`
**Version**: 2.3.0
**Commit**: `8613e6ab1acc37d8795170f9a3ae918725b1f98f`
**LOC**: ~15,000
**Purpose**: Stable, well-known web framework for testing symbol-level retrieval

## Setup

```bash
# Clone and index Flask 2.3.0
git clone https://github.com/pallets/flask.git test-repos/flask
cd test-repos/flask
git checkout 2.3.0

# Index with both models
uv run python -m kb.cli index test-repos/flask --embed-model small
uv run python -m kb.cli index test-repos/flask --embed-model large
```

## Running Evaluation

```bash
# Evaluate all Flask scenarios
just eval-golden --scenarios golden-scenarios-flask/

# Verbose mode
just eval-golden --scenarios golden-scenarios-flask/ --verbose
```

## Scenario Distribution

| Category | Count | Difficulty | Description |
|----------|-------|-----------|-------------|
| Exact Match | 5 | Easy | Class/function name lookups |
| Description-Based | 4 | Medium | Natural language queries |
| Semantic | 3 | Medium/Hard | Architectural concepts |
| Framework-Specific | 2 | Medium | Flask/Werkzeug patterns |
| Navigation | 1 | Hard | Cross-file relationships |

**Total**: 15 scenarios

## Coverage

Tests the following Flask components:
- Core Flask class and decorators
- Request/Response handling
- Blueprint architecture
- URL routing
- Template rendering
- Configuration management
- Error handling
- Context locals
- CLI integration

## Maintenance

- Scenarios are pinned to Flask 2.3.0
- Update scenarios only if test repo version changes
- Add new scenarios for untested patterns
