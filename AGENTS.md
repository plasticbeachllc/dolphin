# Agent Guidelines for Dolphin Repository

This document provides guidelines for LLM agents (Claude, GPT-4, etc.) working in the Dolphin codebase.

## Repository Overview

Dolphin is a semantic code search and knowledge management system for AI interfaces. The project consists of:

- **Python Backend** (`kb/`): FastAPI REST API, knowledge base indexing, embeddings, storage
- **TypeScript MCP Bridge** (`mcp-bridge/`): Model Context Protocol server for AI interfaces
- **Agent Core** (`agent-core/`): Intelligent agent orchestrator with Claude integration
- **VSCode Extension** (`vscode-extension/`): AI coding assistant with SvelteKit webview
- **Documentation** (`docs/`): Architecture, guides, and implementation plans

**Key Documentation:**

- [README.md](README.md) - Project overview, quick start, and user guide
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technical architecture and implementation status
- [TESTING.md](TESTING.md) - Testing setup and procedures

## Core Principles for Agents

### 0. Python Command Execution

**CRITICAL: Always use `uv run` for all Python commands.**

This project uses `uv` for Python dependency management. All Python commands, scripts, and tools MUST be executed using `uv run` to ensure correct dependency resolution and virtual environment activation.

**Examples:**

```bash
# ✅ CORRECT - Use uv run
uv run pytest tests/unit/ -v
uv run python -m black kb/ tests/
uv run python -m mypy kb/
uv run dolphin init
uv run python script.py
uv run ruff check --fix
uv run ruff format
uv run ty check

# ❌ INCORRECT - Do not run Python commands directly
pytest tests/unit/ -v
python -m black kb/ tests/
python -m mypy kb/
dolphin init
python script.py
```

### 1. Documentation Management

**DO NOT create new documentation files unless explicitly requested.**

Dolphin has a mature documentation structure. Instead of creating new files:

- Update existing documentation to reflect changes
- Reference existing docs (ARCHITECTURE.md, README.md, TESTING-GUIDE.md)
- Keep implementation plans in `docs/` updated with current progress

**If you must create documentation:**

- Ask for confirmation first
- Place it in the appropriate location (`docs/` for technical docs)
- Update the main documentation index
- Link from relevant existing documents

### 2. Project Specifications and Plans

**Keep existing specs and implementation plans current.**

The `docs/` directory contains detailed implementation plans and specifications.

**When making changes:**

- Update the relevant plan/spec with completion status
- Mark completed items with ✅
- Update the ARCHITECTURE.md document
- Document any deviations from the original plan

### 3. Test Coverage Requirements

**Ensure comprehensive test coverage for all code changes.**

Dolphin maintains hundreds of passing tests across Python and TypeScript:

**Python Tests** (`tests/`):

- **Unit tests**: `tests/unit/` - Test individual components
- **Integration tests**: `tests/integration/` - Test API endpoints and workflows
- **Run**: `uv run pytest tests/unit/ -v` or `uv run pytest tests/integration/ -v`
- **Coverage**: `uv run pytest --cov=kb/src`

**TypeScript Tests** (`mcp-bridge/`, `agent-core/`):

- **MCP Bridge**: `cd mcp-bridge && bun test`
- **Agent Core**: `cd agent-core && bun test`
- **VSCode Extension**: E2E tests in `vscode-extension/`

**Requirements for code changes:**

1. **New features**: Must include unit tests and integration tests
2. **Bug fixes**: Must include regression tests
3. **Refactoring**: Existing tests must pass
4. **API changes**: Must update integration tests
5. **Aim for**: ≥80% code coverage on new code

**Test checklist:**

```bash
# Before committing, run:
uv run pytest tests/unit/ -v              # Python unit tests
uv run pytest tests/integration/ -v       # Python integration tests
cd mcp-bridge && bun test                 # MCP tests
cd agent-core && bun test                 # Agent tests
just test-all-headless                    # Standard full-suite command for agents (avoids VS Code host)
# Do NOT run `just test-all` in headless/Codex sessions; it requires a VS Code/Electron host.
```

Consider only running relevant test sections in order to take time -- the entire suite is quite lengthy.

### 4. Code Quality Standards

**Language-specific guidelines:**

**Python** (`kb/`, test files):

- Use type hints (SQLModel, Pydantic)
- Use uv for runtime and package management
- Follow PEP 8 style guidelines
- Use pytest for testing with fixtures
- Document complex functions with docstrings
- Use SQLModel for database models

**TypeScript** (`mcp-bridge/`, `agent-core/`, `vscode-extension/`):

- Use strict TypeScript with Zod validation
- Follow the existing code patterns
- Use Bun for runtime and testing
- Document public APIs with JSDoc
- Handle errors with structured error types

**Svelte** (`vscode-extension/webview/`):

- Use SvelteKit conventions
- Follow Tailwind CSS for styling
- Use shadcn/ui components
- Maintain reactive stores for state

### 5. Git Workflow

**Branch naming:**

- Feature branches: `feature/description`
- Bug fixes: `fix/description`
- Documentation: `docs/description`
- Automated branches: `claude/task-name-sessionid`

**Commit messages:**

- Use conventional commits: `type(scope): description`
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
- Examples:
  - `feat(api): add cross-encoder reranking support`
  - `fix(mcp): handle empty search results gracefully`
  - `docs(guide): update installation instructions`
  - `test(chunkers): add tests for SQL chunker`

**Before pushing:**

```bash
# Run tests
uv run pytest tests/ -vx
cd mcp-bridge && bun test
cd agent-core && bun test

# Check code quality
uv run ruff check --fix                    # Format Python
uv run ty check                            # Type check
```

### 6. Architecture Awareness

**Understand the system architecture before making changes:**

```
┌────────────────────────────────────────────┐
│         User Interfaces                    │
│  VSCode Ext | Claude Desktop | CLI         │
└──────┬──────┴──────┬──────────┴────┬───────┘
       │             │               │
       │ JSON-RPC    │ MCP stdio     │ HTTP
       ▼             ▼               ▼
┌──────────────┐  ┌─────────────────────────┐
│ Agent Core   │  │    MCP Bridge           │
│ (Bun/TS)     │  │    (TypeScript/Bun)     │
└──────┬───────┘  └──────────┬──────────────┘
       │                     │
       │ HTTP                │ HTTP
       └─────────────┬───────┘
                     ▼
       ┌──────────────────────────┐
       │   REST API (FastAPI)     │
       │   • Search Backend       │
       │   • Embedding Pipeline   │
       └──────────┬───────────────┘
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
   SQLite    LanceDB      Files
```

**Key components:**

- **REST API** (`kb/api/`): FastAPI server with search endpoints
- **Knowledge Base** (`kb/`): Indexing, chunking, embeddings, storage
- **MCP Bridge** (`mcp-bridge/`): MCP protocol server
- **Agent Core** (`agent-core/`): Claude orchestration and IPC
- **VSCode Extension** (`vscode-extension/`): IDE integration

**Data flow:**

1. **Indexing**: Repository → Scanner → Chunker → Embedder → Storage (SQLite + LanceDB)
2. **Search**: Query → Embed → Vector Search → Re-rank → Response

### 7. Common Tasks

**Adding a new REST API endpoint:**

1. Add route in `kb/api/app.py`
2. Implement handler with proper error handling
3. Add integration test in `tests/integration/api/`
4. Update `README.md` with API documentation if user-facing
5. Consider adding MCP tool if needed

**Adding a new MCP tool:**

1. Create tool in `mcp-bridge/src/mcp/tools/`
2. Register in `mcp-bridge/src/index.ts`
3. Add unit tests in `mcp-bridge/tests/`
4. Update `README.md` with MCP tool documentation
5. Test with MCP Inspector

**Adding a new chunker:**

1. Create chunker in `kb/chunkers/`
2. Register in `kb/chunkers/registry.py`
3. Add unit tests in `tests/unit/chunkers/`
4. Update supported languages in README.md
5. Add integration test with sample files

**Updating the VSCode extension:**

1. Make changes in `vscode-extension/src/` or `vscode-extension/webview/`
2. Build: `npm run build:all`
3. Test in Extension Development Host (F5)
4. Update UI/UX documentation if needed

### 8. Security Considerations

**Always validate user input:**

- Path traversal protection (no `..` in file paths)
- SQL injection prevention (use SQLModel ORM)
- API input validation (Pydantic models)
- Environment variable validation

**Sensitive data:**

- Never commit API keys or secrets
- Use environment variables for credentials
- Respect `.gitignore` patterns in scanner
- Security patterns: `.env`, `.pem`, `.key`, `.aws/`

### 9. Performance Guidelines

**Optimization priorities:**

1. **Search latency**: Target <600ms p50, <2s p95
2. **Indexing speed**: Incremental indexing via git diff
3. **Memory usage**: ~500MB under load
4. **API throughput**: 10-20 QPS sustained

**Performance techniques:**

- Content deduplication via SHA256 hashing
- Batch embedding API calls (100 chunks)
- LanceDB vector search with ANN
- Multi-stage result trimming for MCP
- Caching (in-memory + optional Redis)

### 10. Debugging and Troubleshooting

**Common issues:**

**API not responding:**

```bash
curl http://127.0.0.1:7777/health
# If down: uv run dolphin serve
```

**Tests failing:**

```bash
# Run with verbose output
uv run pytest tests/ -v -s

# Run specific test
uv run pytest tests/unit/chunkers/test_py_chunker.py -v

# Check logs
tail -f mcp-bridge/logs/mcp.log
```

**MCP not connecting:**

```bash
# Test MCP bridge manually
cd mcp-bridge
bun run src/index.ts

# Check Claude Desktop logs
tail -f ~/Library/Logs/Claude/mcp*.log
```

**Index not working:**

```bash
# Check status
uv run dolphin kb status

# Full reindex
uv run dolphin kb index my-repo --full --force

# Check for errors
tail -f ~/.dolphin/knowledge_store/logs/
```

### 11. Release Process

**Version management:**

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md with changes
3. Update version references in documentation
4. Tag release: `git tag v0.1.X`
5. Build: `just build`
6. Deploy: `just deploy-prod`

**Pre-release checklist:**

- [ ] All tests passing (Python + TypeScript)
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Version bumped in pyproject.toml
- [ ] Integration tests with real repos
- [ ] MCP tools tested with Claude Desktop

## Quick Reference Commands

### Development Setup

```bash
# Install dependencies
uv sync --group test
cd mcp-bridge && bun install && cd ..
cd agent-core && bun install && cd ..

# Or use Justfile
just venv            # Create venv and install Python deps
just bun-install     # Install Bun deps for mcp-bridge
```

### Initialize Knowledge Base

```bash
# Using dolphin CLI
uv run dolphin init
uv run dolphin kb add-repo test-repo /path/to/repo
uv run dolphin kb index test-repo

# Using Justfile
just init
just add-repo test-repo /path/to/repo
just index test-repo
just reset test-repo /path/to/repo    # init + add + reindex in one command
```

### Run Services

```bash
# Start services manually
uv run dolphin serve                    # REST API on port 7777

# Or use Justfile
just api                         # Start REST API server
just mcp                         # Start MCP bridge
```

### Run Tests

```bash
# Python tests
uv run pytest tests/unit/ -v            # Unit tests
uv run pytest tests/integration/ -v     # Integration tests
uv run pytest --cov=kb/src              # With coverage

# TypeScript tests
cd mcp-bridge && bun test        # MCP tests
cd agent-core && bun test        # Agent tests
cd vscode-extension && npm test  # Extension tests
```

### Search and Query

```bash
# CLI search
uv run dolphin search "query"
KB_REPOS=my-repo uv run dolphin search "query"  # Filter by repo

# REST API
curl -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "top_k": 5}'

# Using Justfile
just search "query"              # CLI search
just curl-search "query"         # Direct REST search (JSON)
```

### Justfile Development Commands

```bash
# Repository management
just repos                       # List indexed repos
just info                        # Vector store info
just status                      # Check repo status

# Indexing operations
just reindex NAME                # Full reindex (force)
just prune NAME                  # Remove ignored files

# Retrieval operations
just chunk ID                    # Fetch chunk by ID
just lines REPO PATH START END   # Fetch file lines

# Health and monitoring
just health                      # API health check
just tail-mcp                    # View MCP logs

# Cleanup (use with caution)
just store-clean                 # Delete ~/.dolphin/knowledge_store (5s warning)
```

## Troubleshooting Guide

### VSCode Extension Issues

**Extension not connecting to agent:**

```bash
# 1. Check agent-core logs in Output panel (select "Dolphin Agent")
# 2. Verify authentication is set up (Claude CLI or API key)
# 3. Restart extension: Cmd+Shift+P → "Reload Window"
# 4. Check for agent-core process: ps aux | grep agent-core
```

**KB server not starting:**

```bash
# 1. Check if KB is manually running
curl http://127.0.0.1:7777/health

# 2. Check agent logs for KB startup errors
# 3. Manually start KB
uv run dolphin serve

# 4. Verify OPENAI_API_KEY is set
echo $OPENAI_API_KEY
```

**No Knowledge Bank results in chat:**

```bash
# 1. Ensure repositories are indexed
uv run dolphin kb status

# 2. Re-index repository
uv run dolphin kb index <repo-name> --full --force

# 3. Check KB server logs for search errors
tail -f mcp-bridge/logs/mcp.log
```

### API Issues

**API not responding:**

```bash
# Check if API is up
curl http://127.0.0.1:7777/health

# If not, start it
uv run dolphin serve
# Or: just api

# Check for port conflicts
lsof -i :7777
```

**No search results:**

```bash
# Check if repositories are indexed
uv run dolphin kb status

# Re-index repository
uv run dolphin kb index my-repo --full --force

# Try with lower score cutoff
curl -X POST http://127.0.0.1:7777/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "score_cutoff": 0.0, "top_k": 10}'
```

### MCP Issues

**MCP not connecting in Claude Desktop:**

```bash
# 1. Check if API server is running
curl http://127.0.0.1:7777/health

# 2. Check MCP bridge logs
tail -f mcp-bridge/logs/mcp.log

# 3. Check Claude Desktop logs (macOS)
tail -f ~/Library/Logs/Claude/mcp*.log

# 4. Verify Bun is installed
bun --version

# 5. Test MCP server startup
cd mcp-bridge
bun run src/index.ts
# Should start without errors (Ctrl+C to stop)
```

**MCP tools not appearing:**

```bash
# Verify MCP config path (macOS)
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Restart Claude Desktop completely
# Check for 🔌 icon indicating MCP is connected
```

### Test Failures

**Python tests failing:**

```bash
# Run with verbose output
uv run pytest tests/ -v -s

# Run specific test file
uv run pytest tests/unit/chunkers/test_py_chunker.py -v

# Check for missing dependencies
uv sync --group test

# Clear test cache
uv run pytest --cache-clear
```

**TypeScript tests failing:**

```bash
# MCP tests
cd mcp-bridge
bun install
bun test

# Agent tests
cd agent-core
bun install
bun test

# Check for outdated dependencies
bun update
```

### Indexing Issues

**Index not working / taking too long:**

```bash
# Check status
uv run dolphin kb status <repo-name>

# Full reindex with force
uv run dolphin kb index <repo-name> --full --force

# Use smaller embedding model
uv run dolphin kb add-repo my-repo /path --default-embed-model small

# Check for errors in session logs
sqlite3 ~/.dolphin/knowledge_store/knowledge.db \
  "SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1;"
```

**High embedding costs:**

```bash
# Check session costs
uv run dolphin kb status <repo-name>

# Use stub provider for testing (no OpenAI calls)
# Edit ~/.dolphin/config.toml:
# [embedding]
# provider = "stub"

# Reduce chunk size in repo config
# Edit <repo>/.dolphin/config.toml:
# [chunking]
# max_chunk_tokens = 256  # Smaller chunks = fewer embeddings
```

### Import Errors

**Dolphin CLI import error:**

```bash
# If you get ImportError when running dolphin command
# Solution: Use the fixed version
uv pip install --upgrade pb-dolphin

# Or in development:
cd /path/to/dolphin
uv sync --group test
uv run dolphin init
```

**OpenAI API errors:**

```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## Performance Optimization Tips

### Embedding Model Selection

**Choose the right model for your use case:**

- `small` (1536d): Faster, cheaper, good for most use cases (recommended)
- `large` (3072d): More accurate, use for critical repos where precision matters

```bash
# Set per-repository
uv run dolphin kb add-repo critical-app /path --default-embed-model large
uv run dolphin kb add-repo test-repo /path --default-embed-model small
```

### Chunk Size Configuration

**Optimize chunking for your codebase:**

```toml
# <repo>/.dolphin/config.toml
[chunking]
max_chunk_tokens = 256  # Smaller = more chunks, better precision
# max_chunk_tokens = 512  # Larger = fewer chunks, more context
overlap_tokens = 64     # Balance between context and duplication
```

**Trade-offs:**

- Smaller chunks (256 tokens): Better precision, more API calls, higher cost
- Larger chunks (512 tokens): Better context, fewer chunks, lower cost

### Search Optimization

**Filter searches to reduce latency:**

```bash
# Filter by repository
KB_REPOS=api-server uv run dolphin search "auth"

# Filter by path prefix in API call
curl -X POST http://127.0.0.1:7777/search \
  -d '{"query": "auth", "repos": ["api-server"], "path_prefix": ["src/"]}'
```

### Incremental Indexing

**Always use incremental indexing for faster updates:**

```bash
# Incremental (only changed files) - FAST
uv run dolphin kb index my-repo

# Full reindex - SLOW, only when needed
uv run dolphin kb index my-repo --full --force
```

### Cost Monitoring

**Track embedding costs:**

```bash
# Check per-repository costs
uv run dolphin kb status my-repo

# Output shows:
# - Total chunks indexed
# - Tokens used
# - Estimated cost (USD)
```

### LanceDB Performance

**Optimize vector search performance:**

- Smaller collections (< 100K chunks): Fast by default
- Large collections (> 500K chunks): Consider index tuning in LanceDB config
- Memory: Allocate ~500MB for active searches

### Caching Strategy

**Leverage deduplication:**

- Content-based deduplication via SHA256 prevents re-embedding unchanged code
- Git-aware indexing only processes changed files
- Reindexing same code is nearly free

## Getting Help

**Internal resources:**

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design and status
- [README.md](README.md) - Project overview and quick start
- [TESTING.md](TESTING.md) - Testing procedures

**For issues:**

- Check existing GitHub issues: https://github.com/plasticbeachllc/dolphin/issues
- Review relevant test files for examples
- Consult the implementation plans in `docs/`

---

**Remember:** Quality over speed. Take time to understand the architecture, write tests, update documentation, and follow established patterns. The codebase is well-structured - maintain that quality.
