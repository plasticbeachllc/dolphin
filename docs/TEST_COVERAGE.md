# Test Coverage Improvement Plan

## Executive Summary

**Current Status (as of 2025-10-31):**
- **Overall Coverage:** 76% (2316 statements, 564 missed)
- **Tests:** 222 passed, 2 skipped
- **Test Files:** 39 files across unit and integration tests

**Target Goals:**
- **Overall Coverage:** 85%+
- **Critical Path Coverage:** 95%+
- **Tests:** 300+
- **Timeline:** 4-6 weeks

---

## Coverage Analysis by Module

### Critical Gaps (0-60% coverage)

#### 1. CLI Module - **0% coverage** 🔴
**File:** `src/pb_kb/ingest/cli.py` (174 statements, 174 missed)

**Impact:** Highest priority - this is the primary user interface
- No verification that CLI commands work
- No validation of command-line argument parsing
- No error handling validation

**Missing Test Coverage:**
- `kb init` - Initialize knowledge store with config and databases
- `kb add-repo` - Register repositories
- `kb index` - Index repositories with various flags
- `kb status` - Display repository and session status
- `kb prune` - Prune old sessions
- `kb health` - Health check command
- Error handling for invalid inputs
- Flag combinations and validation
- Environment variable handling (OPENAI_API_KEY)

**Test Files Needed:**
- `tests/unit/test_cli.py` - Unit tests for CLI commands
- `tests/integration/test_cli_workflows.py` - Integration tests for CLI workflows

---

#### 2. Ingest Helpers - **56% coverage** 🟡
**File:** `src/pb_kb/ingest/_helpers.py` (45 statements, 20 missed)

**Missing Coverage:**
- `git_changed_files_modified_added()` - Git diff for modified/added files (lines 69-78)
- `git_changed_files_deleted()` - Git diff for deleted files (lines 92-101)
- `get_all_tracked_files()` - Get all tracked files (lines 120-121)
- `representative_text_for_hash()` - Get text for hash (lines 137-140)
- Error handling in git operations (lines 33, 48)

**Test Files Needed:**
- `tests/unit/test_ingest_helpers.py` - Test helper functions

---

#### 3. Pipeline - **60% coverage** 🟡
**File:** `src/pb_kb/ingest/pipeline.py` (203 statements, 81 missed)

**Missing Coverage:**
- Git operations: `_git()`, `_ensure_clean_working_tree()` (lines 40-49)
- Incremental indexing logic (lines 112-123, 133-135)
- Error recovery paths (lines 218-220, 231-237)
- Session management edge cases (lines 292-302, 306-355)
- File deletion handling (lines 366-369, 373-385)
- Dry run mode edge cases (lines 389-397)
- Budget enforcement (lines 413-417)

**Test Files Needed:**
- Expand `tests/integration/test_pipeline.py`
- Add `tests/unit/test_pipeline_git.py` - Test git integration
- Add `tests/unit/test_pipeline_errors.py` - Test error handling

---

#### 4. Ignores - **64% coverage** 🟡
**File:** `src/pb_kb/ignores.py` (36 statements, 13 missed)

**Missing Coverage:**
- `load_repo_ignores()` - Load repo-level ignore patterns (lines 81-98)
- Error handling for malformed TOML (lines 95-98)
- Pattern expansion logic edge cases

**Test Files Needed:**
- `tests/unit/test_ignores.py` - Test ignore pattern loading and expansion

---

### Medium Gaps (70-80% coverage)

#### 5. TypeScript Chunker - **74% coverage** 🟡
**File:** `src/pb_kb/chunkers/ts_chunker.py` (204 statements, 53 missed)

**Missing Coverage:**
- Symbol extraction edge cases (lines 68, 72-73, 77-78)
- Error handling in parsing (lines 90, 92-94)
- Fallback scenarios (lines 291-310, 318-321)
- Symbol path construction (lines 359-374, 377-392, 395-410)
- Edge cases in chunking (lines 442-444)

**Test Files Needed:**
- Expand `tests/unit/test_chunkers/test_ts_chunker.py`

---

#### 6. Markdown Chunker - **76% coverage** 🟡
**File:** `src/pb_kb/chunkers/md_chunker.py` (178 statements, 43 missed)

**Missing Coverage:**
- Front matter parsing edge cases (line 104, 137, 141, 154, 164-165)
- Section scanning edge cases (lines 250-260, 265-271)
- Heading extraction (lines 281-290, 295-305)
- Setext heading handling (line 177)

**Test Files Needed:**
- Expand `tests/unit/test_chunkers/test_md_chunker.py`

---

#### 7. Chunker Registry - **77% coverage** 🟡
**File:** `src/pb_kb/chunkers/registry.py` (97 statements, 22 missed)

**Missing Coverage:**
- Custom chunker loading from config (lines 125-130, 139, 143-144)
- Per-file config override (lines 151-152, 163-165)
- Language detection edge cases (lines 200-203)
- Chunk file with config (lines 312-314, 329)

**Test Files Needed:**
- Expand `tests/unit/test_chunker_registry.py`

---

#### 8. Config - **78% coverage** 🟡
**File:** `src/pb_kb/config.py` (46 statements, 10 missed)

**Missing Coverage:**
- Config loading error handling (lines 82-89)
- Path resolution edge cases (lines 9-10)

**Test Files Needed:**
- `tests/unit/test_config.py` - Test config loading and validation

---

#### 9. API Server - **79% coverage** 🟡
**File:** `src/pb_kb/api/server.py` (43 statements, 9 missed)

**Missing Coverage:**
- Server startup/shutdown (lines 62-65, 82-88, 98)

**Test Files Needed:**
- Expand `tests/unit/test_api_server.py`

---

#### 10. Token Utils - **79% coverage** 🟡
**File:** `src/pb_kb/chunkers/token_utils.py` (66 statements, 14 missed)

**Missing Coverage:**
- Edge cases in tokenization (lines 39, 41, 43, 87-97)

**Test Files Needed:**
- Expand `tests/unit/test_token_utils.py`

---

#### 11. SQLite Metadata Store - **81% coverage** 🟡
**File:** `src/pb_kb/store/sqlite_meta.py` (266 statements, 50 missed)

**Missing Coverage:**
- Error handling in database operations (lines 34-35, 50, 85)
- Session management edge cases (lines 111-113, 160, 186-187)
- Chunk occurrence management (lines 224-230, 308-318)
- Repository deletion (lines 347-349, 357)
- Session pruning (lines 453, 475-477, 497, 521-523)
- Statistics tracking (lines 538-540, 553, 574-576, 603, 625-631, 641-647)

**Test Files Needed:**
- Expand `tests/unit/test_store/test_sqlite_meta.py`

---

#### 12. Repo Config - **82% coverage** 🟡
**File:** `src/pb_kb/chunkers/repo_config.py` (67 statements, 12 missed)

**Missing Coverage:**
- Config loading edge cases (lines 17-18, 130-131, 136, 145)
- Error handling (lines 148-151, 158, 164, 169-172)

**Test Files Needed:**
- Expand `tests/unit/test_repo_config.py`

---

#### 13. Scanner - **84% coverage** 🟢
**File:** `src/pb_kb/ingest/scanner.py` (83 statements, 13 missed)

**Missing Coverage:**
- Edge cases in file scanning (lines 31-32, 44-45, 68, 72-73, 95, 102, 105, 109, 113-114)

**Test Files Needed:**
- Expand `tests/unit/test_scanner.py`

---

#### 14. API App - **85% coverage** 🟢
**File:** `src/pb_kb/api/app.py` (148 statements, 22 missed)

**Missing Coverage:**
- Health check deep mode (lines 95-98)
- Error handling (lines 105, 118, 172-173, 180)
- MCP endpoint edge cases (lines 212-213, 220-221, 233, 258, 270, 286-287, 291-292, 296-298, 302)

**Test Files Needed:**
- `tests/unit/test_api_app.py` - Test FastAPI endpoints
- `tests/integration/test_api_e2e.py` - End-to-end API tests

---

#### 15. Deduplication - **88% coverage** 🟢
**File:** `src/pb_kb/ingest/dedup.py` (33 statements, 4 missed)

**Missing Coverage:**
- Edge cases in deduplication (lines 63-66)

**Test Files Needed:**
- Expand `tests/unit/test_dedup.py`

---

### Good Coverage (90%+ coverage) ✅

The following modules have excellent coverage and only need minor improvements:

- **Fallback Chunker** - 93% (src/pb_kb/chunkers/fallback_chunker.py)
- **Python Chunker** - 93% (src/pb_kb/chunkers/py_chunker.py)
- **Embeddings Provider** - 95% (src/pb_kb/embeddings/provider.py)
- **LanceDB Store** - 95% (src/pb_kb/store/lancedb_store.py)
- **Error Logging** - 96% (src/pb_kb/ingest/error_logging.py)
- **Hashing** - 97% (src/pb_kb/hashing.py)
- **Rankers** - 98% (src/pb_kb/retrieval/rankers.py)
- **Search Backend** - 100% (src/pb_kb/api/search_backend.py)
- **SQL Models** - 100% (src/pb_kb/store/sql_models.py)

---

## Implementation Roadmap

### Phase 1: CLI Testing (Week 1-2) 🔴 **Critical**

**Priority:** Highest - CLI is the primary user interface

**Files to Create:**
```
tests/unit/test_cli.py
tests/integration/test_cli_workflows.py
```

**Test Coverage:**
1. **Command: `kb init`**
   - Creates config directory and files
   - Initializes SQLite database
   - Initializes LanceDB collections
   - Idempotent (can run multiple times safely)
   - Error handling for permission errors
   - Custom config path support

2. **Command: `kb add-repo`**
   - Registers new repository
   - Validates repository path exists
   - Validates repository is a git repository
   - Sets default embed model
   - Handles duplicate repositories
   - Error handling for invalid paths

3. **Command: `kb index`**
   - Basic indexing workflow
   - `--full-reindex` flag
   - `--dry-run` flag
   - `--force` flag
   - `--embed-model` override
   - `--from-commit` incremental indexing
   - Dirty working tree detection
   - Session tracking
   - Error recovery

4. **Command: `kb status`**
   - Shows repository status
   - Shows file counts
   - Shows session history
   - Handles non-existent repository

5. **Command: `kb prune`**
   - Removes old sessions
   - Safety validation
   - Updates counters

6. **Command: `kb health`**
   - System health check
   - Database connectivity
   - Embedding provider status

**Estimated Effort:** 16-24 hours
**Impact:** +174 statements covered (7.5% overall coverage increase)

---

### Phase 2: Configuration & Ignores (Week 2-3) 🟡 **High Priority**

**Files to Create:**
```
tests/unit/test_config.py
tests/unit/test_ignores.py
```

**Test Coverage:**
1. **Config Module**
   - Load config from default path
   - Load config from custom path
   - Config file doesn't exist (use defaults)
   - Invalid TOML syntax
   - Invalid config values
   - Path expansion and resolution
   - Environment variable substitution
   - Config merging (global + repo-specific)

2. **Ignores Module**
   - Default ignore patterns
   - Load repo-level ignores from `.dolphin/config.toml`
   - Pattern expansion (e.g., `foo` → `**/foo`)
   - Malformed TOML handling
   - Missing config file handling
   - Pattern matching validation

**Estimated Effort:** 8-12 hours
**Impact:** +23 statements covered (1% overall coverage increase)

---

### Phase 3: Pipeline & Helpers (Week 3-4) 🟡 **High Priority**

**Files to Create/Expand:**
```
tests/unit/test_ingest_helpers.py
tests/unit/test_pipeline_git.py
tests/unit/test_pipeline_errors.py
tests/integration/test_pipeline.py (expand)
```

**Test Coverage:**
1. **Ingest Helpers**
   - `build_desired_map()` with various chunk types
   - `git_changed_files_modified_added()` with different commit ranges
   - `git_changed_files_deleted()` with deletions
   - `get_all_tracked_files()` in various repo states
   - `representative_text_for_hash()` with valid/invalid hashes
   - Git subprocess error handling

2. **Pipeline Git Integration**
   - `_git()` command execution
   - `_ensure_clean_working_tree()` with clean/dirty states
   - Working tree with uncommitted changes
   - Detached HEAD state
   - Empty repository (no commits)
   - Submodule handling

3. **Pipeline Error Handling**
   - Chunking failures
   - Embedding failures with retry
   - Storage failures
   - File permission errors
   - Disk space exhaustion
   - Concurrent access conflicts
   - Session state recovery

4. **Pipeline Full Workflows**
   - Full reindex workflow
   - Incremental indexing from commit
   - Dry run mode
   - Force mode
   - File deletion handling
   - Budget cap enforcement
   - Session lifecycle (running → succeeded → failed)

**Estimated Effort:** 20-30 hours
**Impact:** +101 statements covered (4.4% overall coverage increase)

---

### Phase 4: API Testing (Week 4-5) 🟡 **Medium Priority**

**Files to Create/Expand:**
```
tests/unit/test_api_app.py
tests/integration/test_api_e2e.py
tests/unit/test_api_server.py (expand)
```

**Test Coverage:**
1. **API Endpoints**
   - `POST /v1/search` with valid query
   - `POST /v1/search` with filters (repos, path_prefix)
   - `POST /v1/search` with parameters (top_k, score_cutoff, etc.)
   - `POST /v1/search` error cases (invalid query, missing fields)
   - `GET /v1/health` shallow check
   - `GET /v1/health?check=deep` with all checks
   - MCP endpoints: search_knowledge, fetch_chunk, fetch_lines
   - MCP endpoints: open_in_editor, get_vector_store_info, get_metadata
   - Request validation
   - Response structure validation
   - Error responses (400, 404, 500)

2. **API Server**
   - Server startup/shutdown
   - Store initialization
   - Graceful shutdown
   - Error handling during startup

3. **End-to-End API**
   - Full workflow: index → search → retrieve
   - Multi-repo search
   - Path filtering
   - Pagination (if implemented)
   - Performance under load

**Estimated Effort:** 16-24 hours
**Impact:** +31 statements covered (1.3% overall coverage increase)

---

### Phase 5: Chunker Edge Cases (Week 5-6) 🟢 **Lower Priority**

**Files to Expand:**
```
tests/unit/test_chunkers/test_ts_chunker.py
tests/unit/test_chunkers/test_md_chunker.py
tests/unit/test_chunker_registry.py
tests/unit/test_token_utils.py
```

**Test Coverage:**
1. **TypeScript Chunker**
   - Parse errors and fallback
   - Empty files
   - Files with no extractable symbols
   - Large files (>10k lines)
   - JSX/TSX specific syntax
   - Decorator syntax
   - Async/await patterns
   - Symbol path construction edge cases

2. **Markdown Chunker**
   - Front matter variations (YAML, TOML)
   - Malformed front matter
   - Setext headings
   - Nested headings beyond h3
   - Empty sections
   - Large documents
   - Code blocks within sections
   - Tables and special syntax

3. **Chunker Registry**
   - Custom chunker loading from `.dolphin/chunking_config.toml`
   - Per-file config overrides
   - Language detection for edge cases
   - Unsupported file types
   - Config validation

4. **Token Utils**
   - Edge cases in windowing
   - Overlap edge cases
   - Very large/small token targets
   - Unicode handling
   - Empty text

**Estimated Effort:** 16-24 hours
**Impact:** +79 statements covered (3.4% overall coverage increase)

---

### Phase 6: Storage & Deduplication (Week 6) 🟢 **Lower Priority**

**Files to Expand:**
```
tests/unit/test_store/test_sqlite_meta.py
tests/unit/test_store/test_lancedb_store.py
tests/unit/test_dedup.py
```

**Test Coverage:**
1. **SQLite Metadata Store**
   - Error handling in all CRUD operations
   - Database locking scenarios
   - Corrupted database recovery
   - Session pruning with various filters
   - Statistics tracking accuracy
   - Chunk occurrence management edge cases
   - Repository deletion with cascading
   - Transaction rollback scenarios

2. **LanceDB Store**
   - Connection failures
   - Index corruption
   - Large batch inserts
   - Query performance edge cases

3. **Deduplication**
   - Hash collision handling
   - Large deduplication sets
   - Memory efficiency with many duplicates

**Estimated Effort:** 12-16 hours
**Impact:** +54 statements covered (2.3% overall coverage increase)

---

## Test Infrastructure Improvements

### 1. Fixtures & Test Data

**Create:**
```
tests/fixtures/
├── repos/
│   ├── simple_python/       - Basic Python repo
│   ├── simple_typescript/   - Basic TypeScript repo
│   ├── markdown_docs/       - Markdown documentation repo
│   ├── mixed_language/      - Multi-language repo
│   ├── large_repo/          - Large repo (1000+ files)
│   └── repo_with_errors/    - Repo with problematic files
├── configs/
│   ├── valid_config.toml
│   ├── minimal_config.toml
│   ├── full_config.toml
│   └── invalid_configs/
│       ├── malformed.toml
│       ├── invalid_values.toml
│       └── missing_required.toml
└── sample_files/
    ├── sample.py
    ├── sample.ts
    ├── sample.tsx
    ├── sample.md
    └── sample.js
```

**Shared Fixtures (conftest.py):**
- `temp_dir()` - Temporary directory for test isolation
- `temp_db_path()` - Temporary SQLite database
- `sample_repo()` - Git repository with sample files
- `mock_embedding_service()` - Mock for OpenAI embeddings
- `test_config()` - Test configuration object
- `lance_store()` - In-memory LanceDB store
- `metadata_store()` - Initialized SQLite metadata store

---

### 2. Testing Utilities

**Create:**
```
tests/utils/
├── git_helpers.py         - Git repository setup helpers
├── assertion_helpers.py   - Custom assertions
├── fixture_builders.py    - Programmatic fixture generation
└── mock_services.py       - Mock service implementations
```

---

### 3. Coverage Tracking

**Setup:**
```bash
# Generate HTML coverage report
uv run pytest --cov=src/pb_kb --cov-report=html --cov-report=term-missing

# Fail if coverage drops below threshold
uv run pytest --cov=src/pb_kb --cov-fail-under=85

# Coverage for specific modules
uv run pytest --cov=src/pb_kb/ingest --cov-report=term-missing tests/unit/test_cli.py
```

**Coverage Badges:**
- Add coverage badge to README.md
- Track coverage trends over time
- Set up coverage reporting in CI/CD

---

### 4. CI/CD Integration

**GitHub Actions Workflow:**
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install uv
          uv sync --group test
      - name: Run tests with coverage
        run: |
          uv run pytest --cov=src/pb_kb --cov-report=xml --cov-fail-under=85
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
```

---

## Testing Best Practices

### 1. Test Organization
- **Unit tests**: Fast (<100ms), isolated, no external dependencies
- **Integration tests**: Medium speed (100ms-1s), real components, temporary state
- **E2E tests**: Slower (>1s), full stack, realistic workflows

### 2. Test Naming Convention
```python
def test_<function>_<scenario>_<expected_result>():
    # Example: test_chunk_markdown_with_front_matter_extracts_title()
    pass
```

### 3. AAA Pattern (Arrange-Act-Assert)
```python
def test_example():
    # Arrange: Set up test data
    repo = create_test_repo()

    # Act: Execute the function under test
    result = scan_repo(repo)

    # Assert: Verify the outcome
    assert len(result) > 0
    assert all(f.path.exists() for f in result)
```

### 4. Fixture Usage
- Use `conftest.py` for shared fixtures
- Scope fixtures appropriately (function, module, session)
- Clean up resources in fixture teardown

### 5. Mocking Strategy
- Mock external services (OpenAI, network calls)
- Don't mock core business logic
- Use real databases for integration tests (with temp files)

### 6. Error Testing
- Test happy path AND error paths
- Test edge cases (empty input, None, invalid types)
- Test error messages are helpful

### 7. Determinism
- No random data without seeding
- No time-dependent logic without mocking
- No network calls without mocking

---

## Success Metrics

### Coverage Targets
- **Overall Coverage:** 85% → **Current: 76%** (Need: +9%)
- **CLI Module:** 90% → **Current: 0%** (Need: +90%)
- **API Module:** 90% → **Current: 85%** (Need: +5%)
- **Pipeline:** 85% → **Current: 60%** (Need: +25%)
- **Config/Ignores:** 85% → **Current: 64-78%** (Need: +7-21%)

### Test Count Targets
- **Current:** 222 tests
- **Target:** 300+ tests
- **Need:** +78 tests minimum

### Module-Specific Targets
| Module | Current | Target | New Tests Needed |
|--------|---------|--------|------------------|
| CLI | 0 | 40 | 40 |
| Pipeline | 5 | 20 | 15 |
| Config/Ignores | 5 | 15 | 10 |
| API | 15 | 25 | 10 |
| Chunkers | 50 | 65 | 15 |
| Storage | 20 | 30 | 10 |

### Quality Metrics
- All tests pass consistently (no flaky tests)
- Test suite runs in <30 seconds
- No test dependencies (can run in any order)
- High-quality error messages
- Comprehensive edge case coverage

---

## Timeline Summary

| Phase | Duration | Effort | Coverage Gain | Priority |
|-------|----------|--------|---------------|----------|
| Phase 1: CLI Testing | Week 1-2 | 16-24h | +7.5% | Critical |
| Phase 2: Config/Ignores | Week 2-3 | 8-12h | +1.0% | High |
| Phase 3: Pipeline/Helpers | Week 3-4 | 20-30h | +4.4% | High |
| Phase 4: API Testing | Week 4-5 | 16-24h | +1.3% | Medium |
| Phase 5: Chunker Edge Cases | Week 5-6 | 16-24h | +3.4% | Lower |
| Phase 6: Storage/Dedup | Week 6 | 12-16h | +2.3% | Lower |
| **Total** | **6 weeks** | **88-130h** | **+19.9%** | |

**Final Projected Coverage: 95.9%**

---

## Quick Wins (Week 0)

Before starting the full roadmap, these can be done in 1-2 days:

1. **Add `tests/unit/test_ignores.py`** (2 hours)
   - Test `build_ignore_set()` with various patterns
   - Test `load_repo_ignores()` with valid/invalid configs
   - **Coverage gain:** +1%

2. **Add `tests/unit/test_config.py`** (2 hours)
   - Test `load_config()` with valid/invalid paths
   - Test `KBConfig.from_mapping()` with various inputs
   - **Coverage gain:** +0.4%

3. **Expand `tests/unit/test_ingest_helpers.py`** (3 hours)
   - Test all git helper functions
   - Test `build_desired_map()` with edge cases
   - **Coverage gain:** +0.9%

4. **Add basic CLI smoke tests** (3 hours)
   - Test `kb init` creates necessary files
   - Test `kb --help` returns usage
   - **Coverage gain:** +0.7%

**Total Quick Wins: 10 hours, +3% coverage**

---

## Maintenance Plan

### Weekly
- Run full test suite before commits
- Review coverage reports
- Add tests for bug fixes

### Monthly
- Review uncovered code
- Update test fixtures
- Benchmark test suite performance

### Quarterly
- Full coverage review
- Update this improvement plan
- Set new coverage targets
- Review and update test infrastructure

---

## References

- **Coverage Report:** Run `uv run pytest --cov=src/pb_kb --cov-report=html`
- **Test README:** [tests/README.md](../tests/README.md)
- **Existing Coverage Plan:** [tests/COVERAGE_IMPROVEMENT_PLAN.md](../tests/COVERAGE_IMPROVEMENT_PLAN.md)
- **Architecture:** [docs/ARCHITECTURE.md](ARCHITECTURE.md)

---

## Appendix: Test Template Examples

### CLI Test Template
```python
# tests/unit/test_cli.py
import pytest
from pathlib import Path
from typer.testing import CliRunner
from pb_kb.ingest.cli import app

runner = CliRunner()

def test_init_creates_config_directory(tmp_path):
    """Test kb init creates necessary directories and files."""
    config_path = tmp_path / "config.toml"
    result = runner.invoke(app, ["init", "--config-path", str(config_path)])

    assert result.exit_code == 0
    assert config_path.exists()
    assert "Initialized" in result.stdout

def test_add_repo_registers_repository(tmp_path, sample_repo):
    """Test kb add-repo successfully registers a repository."""
    result = runner.invoke(app, ["add-repo", str(sample_repo), "--name", "test-repo"])

    assert result.exit_code == 0
    assert "Registered" in result.stdout
```

### API Test Template
```python
# tests/unit/test_api_app.py
import pytest
from fastapi.testclient import TestClient
from pb_kb.api.app import app

client = TestClient(app)

def test_health_check_returns_ok():
    """Test GET /v1/health returns 200 OK."""
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_search_with_valid_query(indexed_store):
    """Test POST /v1/search with valid query returns results."""
    response = client.post(
        "/v1/search",
        json={"query": "test function", "top_k": 5}
    )

    assert response.status_code == 200
    data = response.json()
    assert "hits" in data
    assert isinstance(data["hits"], list)
```

### Integration Test Template
```python
# tests/integration/test_e2e_workflows.py
import pytest
from pathlib import Path
from pb_kb.ingest.pipeline import IngestionPipeline
from pb_kb.config import KBConfig

def test_full_indexing_workflow(sample_repo, temp_db_path):
    """Test complete workflow: scan → chunk → embed → store."""
    # Setup
    config = KBConfig()
    metadata_store = SQLiteMetadataStore(temp_db_path)
    metadata_store.initialize()
    lance_store = LanceDBStore("memory://test")

    # Create pipeline
    pipeline = IngestionPipeline(config, lance_store, metadata_store)

    # Register repo
    metadata_store.record_repo("test-repo", sample_repo, "small")

    # Index repo
    result = pipeline.scan("test-repo", dry_run=False, force=True)

    # Verify
    assert result["status"] == "completed"
    assert result["files_kept"] > 0
    assert result["chunks_added"] > 0

    # Verify chunks in database
    chunks = metadata_store.get_chunks_for_repo("test-repo")
    assert len(chunks) > 0
```

---

**Document Version:** 1.0
**Last Updated:** 2025-10-31
**Next Review:** 2025-11-14
