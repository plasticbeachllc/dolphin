# Dolphin Test Suite

This directory contains the complete test suite for the dolphin project, organized into unit, integration, and e2e tests.

## Installation

Before running tests, install the test dependencies:

```bash
# Using uv (recommended)
uv sync --group test

# Or using pip
pip install -e '.[test]'
```

**Required test dependencies:**
- `pytest` - Test framework
- `pytest-cov` - Coverage reporting
- `pytest-asyncio` - Async test support
- `pytest-xdist` - Parallel test execution
- `pytest-mock` - Mocking utilities
- `psutil` - System monitoring (for performance tests)
- `httpx` - HTTP client for API tests
- `fakeredis`, `freezegun`, `responses` - Test utilities

## Test Organization

```
tests/
├── unit/              # Unit tests (fast, isolated)
│   ├── test_chunkers/     # Chunker-specific tests
│   └── test_store/        # Storage layer tests
├── integration/       # Integration tests (multiple components)
├── e2e/              # End-to-end tests (full system)
├── fixtures/         # Test fixtures and sample data
├── utils/            # Test utilities and helpers
└── run_tests.py      # Unified test runner
```

## Running Tests

### Quick Start

```bash
# Run all tests
python tests/run_tests.py

# Run only unit tests
python tests/run_tests.py --unit

# Run only integration tests
python tests/run_tests.py --integration

# Run specific test file
python tests/run_tests.py tests/unit/test_hashing.py
```

### Advanced Options

```bash
# Run tests in parallel (faster)
python tests/run_tests.py --parallel

# Generate HTML coverage report
python tests/run_tests.py --html

# Run without coverage (faster)
python tests/run_tests.py --no-coverage

# Quiet mode
python tests/run_tests.py -q

# Run tests matching marker expression
python tests/run_tests.py -m "not slow"
```

### Using pytest directly

You can also use pytest directly for more control:

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=pb_kb/src --cov-report=html

# Run specific test
pytest tests/unit/test_hashing.py::test_hash_stability -v

# Run tests matching pattern
pytest tests/ -k "test_chunker"

# Show all test output
pytest tests/ -s
```

## Test Types

### Unit Tests (`tests/unit/`)

Fast, isolated tests that test individual functions, classes, or modules without external dependencies.

- **Chunker tests**: Test text chunking logic for various languages
- **Store tests**: Test database and storage operations
- **API tests**: Test API server initialization and configuration
- **MCP tests**: Test MCP endpoint functionality

**Characteristics:**
- Fast execution (< 1s per test typically)
- No external services required
- Mock/stub external dependencies
- Test single units of code

### Integration Tests (`tests/integration/`)

Tests that verify multiple components work together correctly, may use test fixtures and mock backends.

- **Indexing tests**: Test complete indexing workflow
- **Pipeline tests**: Test ingestion pipeline components
- **Search tests**: Test search functionality with mock data
- **KB load/search tests**: Test knowledge base operations

**Characteristics:**
- Moderate execution time
- May use temporary databases/files
- Test component interactions
- Use fixtures and test data

### E2E Tests (`tests/e2e/`)

Full system tests that verify end-to-end functionality (currently empty, placeholder for future tests).

## Writing Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test functions: `test_*()` or method names starting with `test_`
- Test classes: `Test*` (PascalCase)

### Example Unit Test

```python
"""Unit tests for hashing functionality."""

from kb.hashing import hash_text


def test_hash_stability():
    """Test that hashing is stable across different newline formats."""
    text1 = "hello\nworld\n"
    text2 = "hello\r\nworld\r\n"

    assert hash_text(text1) == hash_text(text2)
```

### Example Integration Test

```python
"""Integration tests for search functionality."""

import pytest
from tests.kb_utils import kb_backend_context


def test_search_workflow():
    """Test complete search workflow with backend."""
    with kb_backend_context() as backend:
        results = backend.search("test query")
        assert len(results) > 0
```

## Test Fixtures

Common test fixtures are located in:
- `tests/conftest.py` - Global pytest fixtures
- `tests/fixtures/` - Test data and sample files
- `tests/utils/` - Test helper functions

## Coverage Reports

After running tests with coverage enabled, reports are generated in:
- `tests/reports/htmlcov/` - HTML coverage report (open `index.html`)
- `tests/reports/coverage.xml` - XML coverage report (for CI/CD)
- `tests/reports/junit/` - JUnit XML test results (for CI/CD)

## Continuous Integration

The test suite is designed to work with CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: python tests/run_tests.py --parallel

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./tests/reports/coverage.xml
```

## Troubleshooting

### Tests are slow
- Use `--parallel` to run tests in parallel
- Use `--unit` to run only fast unit tests
- Use `--no-coverage` to skip coverage collection

### Import errors
- Ensure you're running from the project root
- Ensure virtual environment is activated
- Run `pip install -e .` to install package in development mode

### Fixture not found
- Check that `conftest.py` files are present in test directories
- Ensure fixture names match between definition and usage

## MCP Tests

MCP (Model Context Protocol) related tests are split across:
- **Python API**: `tests/unit/test_mcp_endpoints.py` - Tests all MCP endpoints
- **TypeScript Bridge**: `mcp-bridge/src/tests/` - Tests MCP bridge implementation

Run MCP Python tests:
```bash
python tests/run_tests.py tests/unit/test_mcp_endpoints.py
```

## Contributing

When adding new tests:
1. Choose the appropriate test type (unit/integration/e2e)
2. Follow the naming conventions
3. Add docstrings to test functions
4. Keep tests focused and isolated
5. Use fixtures for common setup/teardown
6. Run the full test suite before submitting

## Questions?

For issues or questions about testing, please refer to:
- Pytest documentation: https://docs.pytest.org/
- Project issues: https://github.com/your-org/dolphin/issues
