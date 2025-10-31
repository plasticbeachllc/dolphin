# Testing Documentation

## Test Architecture

The Dolphin test suite uses pytest with several key fixtures and mocks to ensure tests run reliably without external dependencies.

### Test Results
- **Total**: 360 passed, 4 skipped
- **Unit tests**: Fast, isolated tests with mocked dependencies
- **Integration tests**: Tests that verify component interaction

---

## Important Test Mocks

### 1. Tiktoken Mock (Tokenization)

**Location**: `tests/conftest.py` - `MockTiktokenEncoding` class

**Why it's mocked**:
- Tiktoken requires downloading encoding data from OpenAI's blob storage
- Network calls in tests are slow and can fail (403 errors, timeouts)
- Tests need to be deterministic and work offline

**How it works**:
```python
# Mock uses 3-character chunks per token (avg)
text = "hello world"
tokens = mock_encoding.encode(text)  # [hash("hel"), hash("lo "), hash("wor"), hash("ld")]
decoded = mock_encoding.decode(tokens)  # "hello world"
```

**⚠️ PRODUCTION CONCERN**:

The mock tokenizer is **fundamentally different** from real tiktoken:
- **Real tiktoken**: Uses OpenAI's cl100k_base encoding (~4 chars/token avg)
- **Mock**: Uses simple 3-char chunks with hash-based token IDs
- **Token counts will differ** between tests and production
- **Text windowing boundaries** will be different in production

**Implications**:
1. Unit tests verify chunking **logic** works correctly
2. Unit tests do NOT verify chunking produces correct **results** for production
3. Token count estimates in tests are approximate
4. Chunk boundaries in tests may differ from production

**Current Implementation**:

The test suite uses a **smart fallback strategy**:

```
┌─────────────────────────────────────────────────┐
│              Test Type Decision Tree            │
├─────────────────────────────────────────────────┤
│                                                  │
│  Unit Tests (tests/unit/)                       │
│    ✓ ALWAYS use mock tiktoken                   │
│    ✓ Fast, offline, deterministic               │
│    ✓ Verify logic, not production results       │
│                                                  │
│  Integration Tests (tests/integration/)         │
│    ┌────────────────────────────────┐           │
│    │ Real tiktoken available?       │           │
│    ├────────────────────────────────┤           │
│    │ YES → Use real tiktoken        │←─────┐    │
│    │       (validates production)   │      │    │
│    │                                │      │    │
│    │ NO  → Use mock tiktoken        │      │    │
│    │       (fallback, warns)        │      │    │
│    └────────────────────────────────┘      │    │
│                                             │    │
└─────────────────────────────────────────────┼────┘
                                              │
                                              │
              ┌───────────────────────────────┘
              │
              │  Download real tiktoken:
              │  python scripts/download_tiktoken.py
              │
              └──> Integration tests use real tiktoken
```

**How to enable real tiktoken for integration tests**:

```bash
# Download tiktoken encoding data (run once)
python scripts/download_tiktoken.py

# Now integration tests will automatically use real tiktoken
pytest tests/integration/

# In environments where download is blocked (403 errors):
# - Integration tests will use mock and emit warnings
# - All tests will still pass
```

**Test Status**:
- ✅ Unit tests: Always use mock (362 tests)
- ✅ Integration tests: Use real if available, mock as fallback
- ✅ Real tiktoken validation: 4 tests in `test_real_tiktoken.py` (skipped if unavailable)
- ✅ Graceful degradation: All tests pass with or without real tiktoken

---

### 2. Git Commit Signing

**Location**: Multiple test files

**Why it's disabled**:
- Test environments may not have GPG keys configured
- Signing servers may be unavailable or require authentication
- Tests create temporary repos that are immediately deleted

**How it's handled**:
```python
# Each test repo disables signing at repo level (not globally)
subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path)
```

**✅ PRODUCTION SAFE**:
- Only affects temporary test repositories
- Does NOT modify global git config
- Production repos use their own git config
- No security implications for production

**Helper function**: `init_test_git_repo()` in `tests/conftest.py`

---

## Best Practices

### Running Tests

```bash
# Fast unit tests (with mocks)
pytest tests/unit/

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=src/pb_kb --cov-report=html

# Specific test
pytest tests/unit/test_scanner.py::TestScannerBasic::test_scan_repo_basic_file_enumeration -v
```

### Adding New Tests

1. **Use fixtures** from `conftest.py`:
   - `temp_dir`: Temporary directory for test files
   - `git_repo`: Pre-configured git repository
   - `mock_tiktoken`: Session-scoped tiktoken mock (autouse)
   - `mock_embedding_service`: Deterministic embeddings

2. **For git repos**, use the helper:
   ```python
   from tests.conftest import init_test_git_repo

   repo_path = temp_dir / "my_repo"
   repo_path.mkdir()
   init_test_git_repo(repo_path)  # Handles git init + config
   ```

3. **For production-critical behavior**, consider integration tests:
   ```python
   @pytest.mark.integration
   @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"),
                       reason="Requires OpenAI API key")
   def test_real_embeddings():
       # Test with real OpenAI API
   ```

---

## Known Limitations

### 1. Mock Tiktoken Token Counts
- Mock uses 3 chars/token (simplified)
- Real tiktoken averages ~4 chars/token for English
- Discrepancy grows with non-English text
- **Impact**: Chunk size estimates in tests may not match production

### 2. Mock Embeddings
- Tests use hash-based deterministic embeddings
- Similarity scores in tests are synthetic
- **Impact**: Search ranking in tests doesn't reflect production behavior

### 3. No Network Testing
- All external APIs are mocked
- **Impact**: Network errors, rate limits, retries not tested in unit tests

---

## Future Improvements

### High Priority
- [ ] Add integration tests with real tiktoken (gated by environment variable)
- [ ] Add integration tests with real OpenAI embeddings (gated by API key)
- [ ] Add performance benchmarks for chunking and search

### Medium Priority
- [ ] Add contract tests to verify mock behavior matches real APIs
- [ ] Add end-to-end tests with full pipeline (scan → chunk → embed → search)
- [ ] Add tests for network failures and retry logic

### Low Priority
- [ ] Add mutation testing to verify test quality
- [ ] Add property-based testing for chunking logic
- [ ] Add load testing for concurrent indexing

---

## Troubleshooting

### Tests failing with "403 Forbidden" for tiktoken
**Cause**: Mock tiktoken is not being applied (session scope issue)
**Fix**: Ensure `conftest.py` is in `tests/` directory and pytest finds it

### Tests failing with "fatal: failed to write commit object"
**Cause**: Git commit signing is enabled but signing server is unavailable
**Fix**: Ensure `init_test_git_repo()` is called for all test repos, or check that repo-level config disables signing

### Tests passing but production behaves differently
**Cause**: Mocks may not accurately reflect production behavior
**Fix**: Add integration tests with real dependencies, or review mock implementation

---

## Related Documentation
- [Architecture](../docs/ARCHITECTURE.md) - System architecture and components
- [Test Coverage Plan](./COVERAGE_IMPROVEMENT_PLAN.md) - Test coverage goals
- [Contributing](../README.md#contributing) - How to contribute tests
