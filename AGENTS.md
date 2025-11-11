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
- [README.md](README.md) - Project overview and quick start
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technical architecture and implementation status
- [docs/GUIDE.md](docs/GUIDE.md) - Complete user guide and API reference
- [docs/TESTING-GUIDE.md](docs/TESTING-GUIDE.md) - Testing setup and procedures

## Core Principles for Agents

### 1. Documentation Management

**DO NOT create new documentation files unless explicitly requested.**

Dolphin has a mature documentation structure. Instead of creating new files:
- Update existing documentation to reflect changes
- Reference existing docs (ARCHITECTURE.md, GUIDE.md, README.md)
- Keep implementation plans in `docs/` updated with current progress

**If you must create documentation:**
- Ask for confirmation first
- Place it in the appropriate location (`docs/` for technical docs)
- Update the main documentation index
- Link from relevant existing documents

### 2. Project Specifications and Plans

**Keep existing specs and implementation plans current.**

The `docs/` directory contains detailed implementation plans and specifications:
- `docs/phase5-implementation-plan.md`
- `docs/phase3-test-coverage.md`
- `docs/conversations-test-suite.md`
- `docs/kb-index/*.md`

**When making changes:**
- Update the relevant plan/spec with completion status
- Mark completed items with ✅
- Update the ARCHITECTURE.md implementation status section
- Document any deviations from the original plan

### 3. Test Coverage Requirements

**Ensure comprehensive test coverage for all code changes.**

Dolphin maintains 243+ passing tests across Python and TypeScript:

**Python Tests** (`tests/`):
- **Unit tests**: `tests/unit/` - Test individual components
- **Integration tests**: `tests/integration/` - Test API endpoints and workflows
- **Run**: `pytest tests/unit/ -v` or `pytest tests/integration/ -v`
- **Coverage**: `pytest --cov=kb/src`

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
pytest tests/unit/ -v              # Python unit tests
pytest tests/integration/ -v       # Python integration tests
cd mcp-bridge && bun test         # MCP tests
cd agent-core && bun test         # Agent tests
```

### 4. Code Quality Standards

**Language-specific guidelines:**

**Python** (`kb/`, test files):
- Use type hints (SQLModel, Pydantic)
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
pytest tests/ -v
cd mcp-bridge && bun test
cd agent-core && bun test

# Check code quality
python -m black kb/ tests/          # Format Python
python -m mypy kb/                  # Type check
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
4. Update `docs/GUIDE.md` API reference section
5. Consider adding MCP tool if needed

**Adding a new MCP tool:**
1. Create tool in `mcp-bridge/src/mcp/tools/`
2. Register in `mcp-bridge/src/index.ts`
3. Add unit tests in `mcp-bridge/tests/`
4. Update `docs/GUIDE.md` MCP tools section
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
# If down: dolphin serve
```

**Tests failing:**
```bash
# Run with verbose output
pytest tests/ -v -s

# Run specific test
pytest tests/unit/chunkers/test_py_chunker.py -v

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
dolphin kb status

# Full reindex
dolphin kb index my-repo --full --force

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

```bash
# Development setup
uv sync --group test
cd mcp-bridge && bun install

# Initialize knowledge base
dolphin init
dolphin kb add-repo test-repo /path/to/repo
dolphin kb index test-repo

# Run services
dolphin serve                    # REST API on port 7777
just mcp                         # MCP bridge

# Run tests
pytest tests/unit/ -v            # Python unit tests
pytest tests/integration/ -v     # Python integration
cd mcp-bridge && bun test        # MCP tests
cd agent-core && bun test        # Agent tests

# Search
dolphin search "query"           # CLI search
curl -X POST http://127.0.0.1:7777/search -d '{"query": "test"}'

# Development tools
just repos                       # List indexed repos
just health                      # Health check
just tail-mcp                    # View MCP logs
```

## Getting Help

**Internal resources:**
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design and status
- [GUIDE.md](docs/GUIDE.md) - User guide and API reference
- [TESTING-GUIDE.md](docs/TESTING-GUIDE.md) - Testing procedures

**For issues:**
- Check existing GitHub issues
- Review relevant test files for examples
- Consult the implementation plans in `docs/`

---

**Remember:** Quality over speed. Take time to understand the architecture, write tests, update documentation, and follow established patterns. The codebase is well-structured—maintain that quality.
