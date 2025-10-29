# Test Coverage Improvement Plan for Dolphin

## Current Status
- **147/147 tests passing** ✅
- Coverage includes: chunkers, hashing, scanning, storage, embeddings retry logic, error logging
- Major gaps: CLI, API, configuration, end-to-end workflows

## Gap Analysis

### 🔴 Critical Gaps (High Priority)

#### 1. CLI Command Testing (Typer)
**Currently:** No tests exist
**Impact:** Users cannot verify CLI works
**Needed:**
- `kb init` — Initialize knowledge store
- `kb add-repo` — Register repository
- `kb index` — Index repository with flags (--full-reindex, --dry-run, --force)
- `kb status` — Show status
- `kb prune` — Prune old sessions
- Error handling for invalid inputs
- Flag combinations and validation

#### 2. API Endpoint Testing (FastAPI)
**Currently:** Stub exists, no tests
**Impact:** Retrieval service cannot be verified
**Needed:**
- `POST /v1/search` — Query endpoint with various filters
- `GET /v1/health` — Health check
- Request validation
- Response structure validation
- Error cases (invalid queries, missing repos, etc.)
- Performance under load

#### 3. End-to-End Workflows
**Currently:** Basic integration tests only
**Impact:** Real-world scenarios not verified
**Needed:**
- Full indexing → storage → retrieval cycle
- Multi-repo scenarios
- Repository with changes detection
- Incremental indexing verification
- Session lifecycle (running → succeeded → new session)

#### 4. Configuration System
**Currently:** Partial testing
**Impact:** Per-repo settings not verified
**Needed:**
- Global config loading (`.dolphin/config.toml`)
- Per-repo config loading (`.dolphin/chunking_config.toml`)
- Config merging (global + per-repo)
- Config validation and defaults
- Invalid config handling
- Path resolution and expansion

### 🟡 Medium Priority Gaps

#### 5. Git Integration Edge Cases
**Currently:** Basic scanning tested
**Needed:**
- Dirty working tree detection
- Submodule handling
- Symlink handling
- Branch switching
- Commit history edge cases
- No commits in repo
- Detached HEAD state

#### 6. Error Scenarios & Recovery
**Currently:** Basic error handling
**Needed:**
- Network failures during embedding
- Corrupted SQLite database
- Invalid LanceDB state
- File permission issues
- Disk space exhaustion
- Concurrent access conflicts
- Graceful degradation

#### 7. Budget & Cost Control
**Currently:** Not tested
**Impact:** Cost enforcement cannot be verified
**Needed:**
- Cost estimation accuracy
- Per-session spend cap enforcement
- Token counting validation
- Backoff logic on rate limits
- Session budget tracking

#### 8. Deduplication & Idempotency
**Currently:** Basic tests exist
**Needed:**
- Content hash collision handling
- Chunk movement detection (same hash, different lines)
- Re-indexing same commit
- Cross-repo deduplication
- Vector reuse scenarios

### 🟢 Nice-to-Have Gaps

#### 9. Performance & Scalability
**Currently:** Not tested
**Needed:**
- Large file processing (>10MB files)
- Large repo processing (10k+ files)
- Memory usage validation
- Concurrent indexing operations
- Query latency benchmarking
- Vector search performance

#### 10. Cross-Platform Behavior
**Currently:** Unix-centric
**Needed:**
- Windows path handling
- macOS specific behavior
- Line ending normalization
- Symlink behavior differences

---

## Recommended Implementation Order

### Phase A: CLI Testing (Week 1)
1. Create `tests/unit/ingest/test_cli.py`
2. Test all CLI commands with fixtures
3. Test flag combinations
4. Test error cases

### Phase B: API Testing (Week 1)
1. Create `tests/unit/api/test_search_endpoint.py`
2. Create `tests/unit/api/test_health_endpoint.py`
3. Test request/response validation
4. Test error cases

### Phase C: End-to-End Workflows (Week 2)
1. Create `tests/integration/test_e2e_index_retrieve.py`
2. Test complete indexing pipeline
3. Test retrieval scenarios
4. Test session lifecycle

### Phase D: Configuration (Week 2)
1. Create `tests/unit/test_config_system.py`
2. Test config loading/merging
3. Test validation
4. Test per-repo overrides

### Phase E: Git Integration (Week 3)
1. Expand `tests/unit/test_scanner.py`
2. Test edge cases
3. Test dirty/clean state detection

### Phase F: Error Scenarios (Week 3)
1. Create `tests/unit/test_error_handling.py`
2. Test recovery mechanisms
3. Test graceful failures

### Phase G: Budget/Cost Control (Week 4)
1. Create `tests/unit/test_budget_enforcement.py`
2. Test cost estimation
3. Test spend cap logic

---

## Test Templates

Here are template files to implement:

### Template 1: CLI Tests
```python tests/unit/ingest/test_cli.py
# tests/unit/ingest/test_cli.py
```

### Template 2: API Tests
```python tests/unit/api/test_app.py
# tests/unit/api/test_app.py
```

### Template 3: E2E Workflow Tests
```python tests/integration/test_e2e_workflows.py
# tests/integration/test_e2e_workflows.py
```

### Template 4: Configuration Tests
```python tests/unit/test_config_system.py
# tests/unit/test_config_system.py
```

---

## Coverage Metrics to Track

### Current Baseline
- Lines of code: ~3,500
- Test files: 20+
- Tests: 147
- Coverage: ~65-70% (estimated)

### Target After Improvements
- Tests: 250+
- Coverage: >85%
- CLI coverage: 100%
- API coverage: 100%
- Error paths: 90%+

---

## Specific Test Cases Needed

### CLI (`kb` command)
```
✓ kb init
  ├─ Creates ~/.dolphin/knowledge_store
  ├─ Creates SQLite DB
  ├─ Creates LanceDB collections
  ├─ Idempotent (can run twice safely)
  └─ Handles permission errors

✓ kb add-repo
  ├─ Registers new repo
  ├─ Validates repo path exists
  ├─ Validates repo is git repository
  ├─ Sets default embed model
  ├─ Duplicate repo handling
  └─ Error on invalid path

✓ kb index <repo>
  ├─ Basic indexing
  ├─ --full-reindex flag
  ├─ --dry-run flag
  ├─ --force flag
  ├─ --embed-model override
  ├─ Dirty tree detection
  ├─ Session tracking
  ├─ Counter updates
  ├─ Incremental indexing
  └─ Error recovery

✓ kb status [repo]
  ├─ Shows repo status
  ├─ Shows file counts
  ├─ Shows session history
  └─ Handles non-existent repo

✓ kb prune
  ├─ Removes old sessions
  ├─ Validates safety
  └─ Updates counters
```

### API (`/v1/search`)
```
✓ POST /v1/search
  ├─ Valid query
  ├─ With repo filter
  ├─ With path prefix filter
  ├─ top_k parameter
  ├─ max_snippet_tokens
  ├─ embed_model selection
  ├─ score_cutoff filtering
  ├─ Multiple repos
  ├─ No results case
  ├─ Invalid query handling
  ├─ Missing required fields
  └─ Malformed JSON

✓ GET /v1/health
  ├─ Returns status OK
  ├─ Returns version info
  ├─ Returns timestamp
  └─ Always responds quickly
```

### Error Scenarios
```
✓ Embedding failures
  ├─ Network timeouts
  ├─ Rate limits (429)
  ├─ Server errors (5xx)
  ├─ Invalid API key
  └─ Retry + backoff

✓ Storage failures
  ├─ SQLite locked/corrupted
  ├─ LanceDB connection error
  ├─ Disk full
  ├─ Permission denied
  └─ Corrupted indices

✓ Input validation
  ├─ Invalid paths
  ├─ Invalid commit SHAs
  ├─ Invalid embed models
  ├─ Invalid token counts
  └─ Oversized queries
```

---

## Quick Wins (Easy to Add)

1. **Config validation tests** (2-3 hours)
   - Load valid/invalid TOML
   - Merge global + per-repo
   - Path expansion
   
2. **Git edge cases** (2-3 hours)
   - Empty repo (no commits)
   - Detached HEAD
   - Multiple branches
   
3. **Snapshot testing** (1-2 hours)
   - Store expected outputs
   - Compare on changes
   - Detect regressions automatically

4. **Fixture expansion** (2-3 hours)
   - Add test repos with various file types
   - Add repos with errors
   - Add repos with large files

---

## Tools & Setup

### Coverage Reporting
```bash
# HTML coverage report
uv run pytest --cov=src/pb_kb --cov-report=html

# Show uncovered lines
uv run pytest --cov=src/pb_kb --cov-report=term-missing
```

### Parallel Testing
```bash
# Run tests in parallel (faster feedback)
uv run pytest -n auto
```

### Fixture Snapshots
```bash
# Update snapshots after validating changes
uv run pytest --snapshot-update
```

---

## Success Criteria

- [ ] All CLI commands have tests with >90% coverage
- [ ] All API endpoints tested with >90% coverage
- [ ] Error paths tested for all major components
- [ ] E2E workflows covering index → retrieve cycle
- [ ] Configuration system fully tested
- [ ] Git edge cases handled
- [ ] Budget/cost enforcement verified
- [ ] Overall test count: 250+
- [ ] Overall coverage: >85%
- [ ] All tests pass in <10 seconds

---

## Files to Create/Modify

```
tests/
├── unit/
│   ├── ingest/
│   │   ├── test_cli.py          (NEW)
│   │   ├── test_pipeline.py     (EXPAND)
│   │   └── test_scanner_edge_cases.py (NEW)
│   ├── api/
│   │   ├── test_search_endpoint.py (NEW)
│   │   └── test_health_endpoint.py (NEW)
│   ├── test_config_system.py    (NEW)
│   ├── test_budget_enforcement.py (NEW)
│   └── test_error_scenarios.py  (NEW)
├── integration/
│   ├── test_e2e_workflows.py    (NEW)
│   ├── test_index_retrieve_cycle.py (NEW)
│   └── test_session_lifecycle.py (NEW)
├── fixtures/
│   ├── repos/
│   │   ├── simple_python/       (NEW)
│   │   ├── simple_typescript/   (NEW)
│   │   ├── large_repo/          (NEW)
│   │   └── repo_with_errors/    (NEW)
│   └── config/
│       ├── valid_config.toml    (NEW)
│       └── invalid_configs/     (NEW)
└── COVERAGE_IMPROVEMENT_PLAN.md (THIS FILE)
```

---

## Maintenance

### Weekly
- Run full test suite
- Check coverage trends
- Review new gaps

### Monthly
- Add tests for bug fixes
- Expand error scenario coverage
- Benchmark performance tests

### Quarterly
- Full coverage review
- Update this plan
- Set new targets
```

Now let me create specific test template files that you can use as starting points. Let me create a comprehensive testing strategy document:

```markdown tests/TESTING_STRATEGY.md
# Dolphin Testing Strategy

## Overview
This document outlines how to systematically improve test coverage across the knowledge store pipeline.

## Testing Pyramid

```
       ╔═══════════╗
       ║  E2E Tests║  (10%) - Full workflows
       ║ (Slow)    ║
       ╠═══════════╣
       ║Integration║  (30%) - Component interaction
       ║   Tests   ║
       ║ (Medium)  ║
       ╠═══════════╣
       ║ Unit Tests║  (60%) - Individual components
       ║  (Fast)   ║
       ╚═══════════╝
```

## Test Categories

### 1. Unit Tests (60% of tests)
- **Fast**: <100ms each
- **Isolated**: Mock dependencies
- **Focused**: One component per test
- **Repeatable**: No side effects

**Coverage areas:**
- Chunkers (py, ts, md, fallback)
- Hashing and canonicalization
- Token utilities
- Configuration loading
- Storage CRUD operations
- Deduplication logic
- Error handling

### 2. Integration Tests (30% of tests)
- **Medium speed**: 100ms-1s each
- **Real components**: Limited mocking
- **Multi-component**: Test interactions
- **Temporary state**: Use temp files/DBs

**Coverage areas:**
- Pipeline scanning + chunking
- Pipeline indexing + storage
- Configuration merging
- Git integration
- Storage layer persistence
- Error recovery workflows

### 3. E2E Tests (10% of tests)
- **Slow**: >1s each (but acceptable)
- **Full stack**: No mocking
- **Real workflows**: Index → retrieve
- **Realistic data**: Sample repos

**Coverage areas:**
- Complete indexing workflows
- Search and retrieval
- Budget enforcement
- Session lifecycle
- Multi-repo scenarios

## Running Tests Effectively

### Fast Feedback Loop (Development)
```bash
# Run only affected tests (fast)
uv run pytest tests/unit/ -k "chunker" --tb=short

# Run with coverage only for changed files
uv run pytest tests/unit/ --cov=src/pb_kb/chunkers
```

### Pre-Commit Check
```bash
# Run all unit tests before committing
uv run pytest tests/unit/ -x  # Stop on first failure

# Check coverage meets threshold
uv run pytest --cov=src/pb_kb --cov-fail-under=80
```

### Full Suite (CI/Pre-Release)
```bash
# Run everything with detailed reporting
uv run pytest tests/ -v --cov=src/pb_kb --cov-report=html --tb=long
```

### Specific Areas
```bash
# CLI testing
uv run pytest tests/unit/ingest/test_cli.py -v

# API testing
uv run pytest tests/unit/api/ -v

# Storage layer
uv run pytest tests/unit/test_store/ -v

# Chunkers
uv run pytest tests/unit/test_chunkers/ -v

# Integration workflows
uv run pytest tests/integration/ -v
```

## Key Testing Principles

### 1. Determinism
- Same test input → same output always
- No flaky tests (timing-dependent)
- Seed random generators

### 2. Isolation
- Tests don't affect each other
- Each test uses temp files/DBs
- Clean up after each test

### 3. Clarity
- Test names describe what's tested
- Comments explain non-obvious logic
- Assertions have helpful messages

### 4. Coverage
- High coverage for critical paths
- Lower coverage OK for edge cases
- Coverage ≠ quality (test good cases too)

### 5. Maintainability
- DRY principle: share fixtures, helpers
- Update tests with code
- Keep fixtures realistic but minimal

## Fixture Strategy

### Shared Fixtures (conftest.py)
```python
# Reusable across many tests
- temp_dir()
- temp_db_path()
- sample_repo_path()
- mock_embedding_service()
- git_repo()
```

### Component-Specific Fixtures
```python
# In component test files
- python_sample_code()
- typescript_sample_code()
- markdown_sample_content()
- valid_config()
- invalid_config()
```

### E2E Fixtures
```python
# In integration test files
- full_sample_repo()
- indexed_sample_repo()
- multi_repo_setup()
```

## Mocking Strategy

### Mock External Services
✅ OpenAI embeddings
✅ LanceDB vector store (use in-memory)
✅ File system (when testing errors)
✅ Git (for specific scenarios)

### Don't Mock
❌ Core pipeline logic
❌ Storage layer (use real SQLite/LanceDB)
❌ Chunkers (test real parsing)
❌ Hashing (test real SHA256)

## Error Testing Checklist

For each component, test:
- [ ] Missing required input
- [ ] Invalid input type
- [ ] Out-of-range values
- [ ] Corrupted data
- [ ] Network failures
- [ ] Permission denied
- [ ] Resource exhaustion
- [ ] Concurrent access
- [ ] Graceful degradation

## Performance Expectations

- **Unit tests**: <5ms per test (200+ tests = ~1s)
- **Integration tests**: 50-500ms per test (20 tests = ~5-10s)
- **E2E tests**: 1-5s per test (5 tests = ~15-25s)
- **Total**: <30 seconds for full suite

## Coverage Goals by Component

| Component | Target | Current | Gap |
|-----------|--------|---------|-----|
| Chunkers | 95% | 85% | -10% |
| Hashing | 95% | 90% | -5% |
| Storage | 90% | 80% | -10% |
| Pipeline | 85% | 70% | -15% |
| CLI | 90% | 0% | -90% |
| API | 90% | 0% | -90% |
| Config | 85% | 60% | -25% |
| Error handling | 80% | 50% | -30% |

## Regression Testing

### Snapshot Testing
Store expected outputs:
```python
def test_chunker_output(snapshot):
    result = chunk_python_code(SAMPLE_CODE)
    assert result == snapshot
    # Will fail if output changes unexpectedly
```

### Golden Files
Keep reference outputs:
```
tests/fixtures/expected_outputs/
├── chunks_py_sample.json
├── chunks_ts_sample.json
└── config_merged.toml
```

### Diff Detection
Compare before/after indexing:
```python
def test_incremental_no_changes():
    result1 = index_repo(repo)
    result2 = index_repo(repo)  # Same repo, no changes
    assert result1 == result2   # Should be identical
```

## Debugging Failed Tests

### Common Issues

**Test hangs**
- Check for deadlocks in concurrent code
- Verify timeouts are set
- Use `pytest --timeout=10` to catch hangs

**Non-deterministic failures (flaky)**
- Check for timing dependencies
- Verify file operations complete
- Look for unsorted iteration

**Out-of-order failures**
- Tests depend on execution order
- Indicates shared state leakage
- Use `pytest --random-order` to detect

### Debugging Techniques

```bash
# Show print statements
uv run pytest tests/unit/test_chunker_registry.py -v -s

# Stop on first failure for immediate debugging
uv run pytest tests/ -x --pdb

# Show full diffs for assertion failures
uv run pytest tests/ -vv

# Run single test with full context
uv run pytest tests/unit/test_hashing.py::test_canonical_whitespace -vv
```

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - run: pip install uv
      - run: uv run pytest tests/ --cov=src/pb_kb --cov-fail-under=80
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Hypothesis property-based testing](https://hypothesis.readthedocs.io/)