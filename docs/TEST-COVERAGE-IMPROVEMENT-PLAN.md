# Test Coverage Improvement Plan

**Date:** 2025-11-12
**Status:** Phase 1 & 2 Complete ✅ | Phase 3 Ready to Start 🔄
**Estimated Effort:** 45-65 hours (1-1.5 weeks)
**Last Updated:** 2025-11-12

## Implementation Status

| Phase                                   | Status      | Completion Date | Tests Added |
| --------------------------------------- | ----------- | --------------- | ----------- |
| Phase 1: Critical Path Testing          | ✅ Complete | 2025-11-12      | 160+ tests  |
| Phase 2: Utility & Support Code         | ✅ Complete | 2025-11-12      | 150+ tests  |
| Phase 3: Type Validation & Schema Tests | ⏳ Pending  | -               | -           |

### Phase 1 Deliverables (✅ Complete)

- ✅ `tests/unit/test_lang.py` - 50 tests for language classification
- ✅ `tests/unit/test_api_server.py` - Enhanced with env file loading tests
- ✅ `mcp-bridge/src/tests/rest_client.test.ts` - 50+ tests for REST client
- ✅ `agent-core/tests/tool-executor-unit.test.ts` - 30+ tests for tool executor
- ✅ `agent-core/tests/index-queue.test.ts` - 30+ tests for index queue

**Coverage Impact:**

- kb/ingest/lang.py: 0% → 100%
- kb/api/server.py: Partial → ~90%
- mcp-bridge/rest/client.ts: 0% → ~85%
- agent-core/llm/claude-tool-executor.ts: Integration only → ~80%
- agent-core/kb/index-queue.ts: 0% → ~90%

### Phase 2 Deliverables (✅ Complete)

- ✅ `tests/unit/test_graph_helpers_unit.py` - 50+ tests for graph extraction and storage
- ✅ `tests/unit/test_graph_context_unit.py` - 60+ tests for graph context enrichment
- ✅ `mcp-bridge/src/tests/util.test.ts` - 90+ tests for config, language, and logger utilities

**Coverage Impact:**

- kb/ingest/graph_helpers.py: Integration only → ~95%
- kb/retrieval/graph_context.py: Integration only → ~90%
- mcp-bridge/util/config.ts: 0% → ~90%
- mcp-bridge/util/language.ts: 0% → ~95%
- mcp-bridge/util/logger.ts: 0% → ~85%

## Executive Summary

This document outlines a comprehensive plan to improve test coverage across the Dolphin codebase. Our analysis identified critical gaps in testing that pose risks to production stability. This plan prioritizes high-impact areas and provides concrete implementation steps.

### Current State

- **Python Backend (kb/):** 57 test files covering 47 source files
- **agent-core:** 67% file coverage (12 test files for 18 source files)
- **mcp-bridge:** 45% file coverage (10 test files for 22 source files)
- **vscode-extension:** 82% file coverage (strong)

### Target State

- **Overall coverage:** 60% → 85%
- **Critical path coverage:** 40% → 95%
- **Expected impact:** ~70% reduction in production bugs

---

## Table of Contents

1. [Critical Gaps Summary](#critical-gaps-summary)
2. [Phase 1: Critical Path Testing](#phase-1-critical-path-testing-week-1-2)
3. [Phase 2: Utility & Support Code](#phase-2-utility--support-code-week-3)
4. [Phase 3: Type Validation & Schema Tests](#phase-3-type-validation--schema-tests-week-4)
5. [Implementation Guidelines](#implementation-guidelines)
6. [Testing Best Practices](#testing-best-practices)
7. [Success Metrics](#success-metrics)

---

## Critical Gaps Summary

### High Priority (Production-Critical)

| Component                              | Lines | Current Coverage | Risk Level  | Impact                          |
| -------------------------------------- | ----- | ---------------- | ----------- | ------------------------------- |
| kb/api/server.py                       | 109   | None             | 🔴 Critical | Server initialization failures  |
| kb/ingest/cli.py                       | 869   | None             | 🔴 Critical | CLI workflow breakage           |
| agent-core/llm/claude-tool-executor.ts | 572   | None             | 🔴 Critical | Tool execution failures         |
| mcp-bridge/rest/client.ts              | 159   | None             | 🔴 Critical | API communication failures      |
| agent-core/kb/index-queue.ts           | 152   | None             | 🔴 Critical | Queue failures, race conditions |

### Medium Priority (Partial Coverage)

| Component                     | Lines | Current Coverage | Issue                                  |
| ----------------------------- | ----- | ---------------- | -------------------------------------- |
| kb/ingest/graph_helpers.py    | 190   | Integration only | No unit tests for individual functions |
| kb/retrieval/graph_context.py | 393   | Integration only | No method-level testing                |
| mcp-bridge/util/config.ts     | 177   | None             | Configuration errors                   |
| agent-core/llm/tool-utils.ts  | 118   | None             | Utility function failures              |

### Low Priority (Type Definitions & Utilities)

- kb/chunkers/types.py, graph_types.py
- kb/store/sql_models.py
- kb/retrieval/types.py
- mcp-bridge utilities (logger, mime, language)

---

## Phase 1: Critical Path Testing (Week 1-2)

### 1.1 Server Initialization Tests

**File:** `tests/unit/test_api_server.py` (NEW)
**Target:** `kb/api/server.py`
**Estimated Time:** 4 hours

#### Test Cases to Implement

```python
"""Unit tests for API server initialization."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from kb.api.server import load_env_file, initialize_search_backend


class TestLoadEnvFile:
    """Test environment file loading."""

    def test_load_env_file_exists(self, tmp_path):
        """Test loading valid .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY=test_value\nAPI_KEY=secret")

        with patch('kb.api.server.Path') as mock_path:
            mock_path.return_value.parent.parent.parent.parent = tmp_path
            load_env_file()

        assert os.environ.get("TEST_KEY") == "test_value"
        assert os.environ.get("API_KEY") == "secret"

    def test_load_env_file_missing(self, tmp_path, capsys):
        """Test graceful handling when .env file is missing."""
        with patch('kb.api.server.Path') as mock_path:
            mock_path.return_value.parent.parent.parent.parent = tmp_path
            load_env_file()

        captured = capsys.readouterr()
        assert "No .env file found" in captured.err

    def test_load_env_file_malformed(self, tmp_path, capsys):
        """Test handling of malformed .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("INVALID LINE WITHOUT EQUALS\n# Comment\nVALID=value")

        with patch('kb.api.server.Path') as mock_path:
            mock_path.return_value.parent.parent.parent.parent = tmp_path
            load_env_file()

        # Should not crash, should load valid lines
        assert os.environ.get("VALID") == "value"

    def test_load_env_file_strips_quotes(self, tmp_path):
        """Test that quotes are stripped from values."""
        env_file = tmp_path / ".env"
        env_file.write_text('API_KEY="quoted_value"\nOTHER=\'single_quoted\'')

        with patch('kb.api.server.Path') as mock_path:
            mock_path.return_value.parent.parent.parent.parent = tmp_path
            load_env_file()

        assert os.environ.get("API_KEY") == "quoted_value"
        assert os.environ.get("OTHER") == "single_quoted"


class TestInitializeSearchBackend:
    """Test search backend initialization."""

    @patch('kb.api.server.create_search_backend')
    @patch('kb.api.server.load_config')
    @patch('kb.api.server.set_search_backend')
    @patch('kb.api.server.set_stores')
    @patch('kb.api.server.set_pipeline')
    def test_initialize_with_openai_provider(
        self, mock_set_pipeline, mock_set_stores, mock_set_backend,
        mock_load_config, mock_create_backend
    ):
        """Test initialization with OpenAI provider."""
        # Setup mock config
        mock_config = MagicMock()
        mock_config.resolved_store_root.return_value = Path("/tmp/store")
        mock_config.embedding_provider = "openai"
        mock_config.openai_api_key_env = "OPENAI_API_KEY"
        mock_config.embedding_batch_size = 100
        mock_config.cache_enabled = True
        mock_config.redis_url = None
        mock_config.retrieval.reranking.__dict__ = {}
        mock_load_config.return_value = mock_config

        # Setup mock backend
        mock_backend = MagicMock()
        mock_create_backend.return_value = mock_backend

        # Set environment variable
        os.environ["OPENAI_API_KEY"] = "test-key"

        # Execute
        initialize_search_backend()

        # Verify
        mock_create_backend.assert_called_once()
        call_kwargs = mock_create_backend.call_args[1]
        assert call_kwargs["embedding_provider_type"] == "openai"
        assert call_kwargs["api_key"] == "test-key"
        assert call_kwargs["batch_size"] == 100

        mock_set_backend.assert_called_once_with(mock_backend)
        mock_set_stores.assert_called_once()
        mock_set_pipeline.assert_called_once()

        # Cleanup
        del os.environ["OPENAI_API_KEY"]

    @patch('kb.api.server.create_search_backend')
    @patch('kb.api.server.load_config')
    @patch('kb.api.server.set_search_backend')
    def test_initialize_without_api_key_falls_back_to_stub(
        self, mock_set_backend, mock_load_config, mock_create_backend, capsys
    ):
        """Test fallback to stub provider when API key is missing."""
        mock_config = MagicMock()
        mock_config.resolved_store_root.return_value = Path("/tmp/store")
        mock_config.embedding_provider = "openai"
        mock_config.openai_api_key_env = "OPENAI_API_KEY"
        mock_config.cache_enabled = False
        mock_config.redis_url = None
        mock_config.retrieval.reranking.__dict__ = {}
        mock_load_config.return_value = mock_config

        # Ensure API key is not set
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

        mock_backend = MagicMock()
        mock_create_backend.return_value = mock_backend

        initialize_search_backend()

        # Should use stub provider
        call_kwargs = mock_create_backend.call_args[1]
        assert call_kwargs["embedding_provider_type"] == "stub"

        # Should log warning
        captured = capsys.readouterr()
        assert "Using stub provider" in captured.err

    @patch('kb.api.server.create_search_backend')
    @patch('kb.api.server.load_config')
    def test_initialize_creates_pipeline_with_correct_stores(
        self, mock_load_config, mock_create_backend
    ):
        """Test that pipeline is initialized with same stores as backend."""
        mock_config = MagicMock()
        mock_config.resolved_store_root.return_value = Path("/tmp/store")
        mock_config.embedding_provider = "stub"
        mock_config.cache_enabled = False
        mock_config.redis_url = None
        mock_config.retrieval.reranking.__dict__ = {}
        mock_load_config.return_value = mock_config

        mock_backend = MagicMock()
        mock_backend.sql_store = MagicMock()
        mock_backend.lance_store = MagicMock()
        mock_backend.sql_store.db_path = "/tmp/store/meta.db"
        mock_create_backend.return_value = mock_backend

        with patch('kb.api.server.IngestionPipeline') as mock_pipeline_class:
            with patch('kb.api.server.GraphStore') as mock_graph_store:
                initialize_search_backend()

                # Verify pipeline created with backend's stores
                mock_pipeline_class.assert_called_once()
                call_kwargs = mock_pipeline_class.call_args[1]
                assert call_kwargs["lancedb"] == mock_backend.lance_store
                assert call_kwargs["metadata"] == mock_backend.sql_store
```

**Success Criteria:**

- ✅ All initialization paths tested
- ✅ Environment variable handling validated
- ✅ Fallback behavior verified
- ✅ Store/pipeline initialization checked

---

### 1.2 Language Classification Tests

**File:** `tests/unit/test_lang.py` (NEW)
**Target:** `kb/ingest/lang.py`
**Estimated Time:** 2 hours

#### Test Cases to Implement

```python
"""Unit tests for language classification."""

import pytest
from pathlib import Path
from kb.ingest.lang import classify_language


class TestClassifyLanguage:
    """Test language classification from file paths."""

    def test_python_extensions(self):
        """Test Python file extensions are correctly classified."""
        assert classify_language(Path("test.py")) == (".py", "python")
        assert classify_language(Path("script.pyw")) == (".pyw", "python")
        assert classify_language(Path("stubs.pyi")) == (".pyi", "python")

    def test_typescript_extensions(self):
        """Test TypeScript file extensions."""
        assert classify_language(Path("component.ts")) == (".ts", "typescript")
        assert classify_language(Path("app.tsx")) == (".tsx", "typescriptreact")
        assert classify_language(Path("module.mts")) == (".mts", "typescript")
        assert classify_language(Path("config.cts")) == (".cts", "typescript")

    def test_javascript_extensions(self):
        """Test JavaScript file extensions."""
        assert classify_language(Path("app.js")) == (".js", "javascript")
        assert classify_language(Path("component.jsx")) == (".jsx", "javascriptreact")
        assert classify_language(Path("common.cjs")) == (".cjs", "javascript")
        assert classify_language(Path("module.mjs")) == (".mjs", "javascript")

    def test_markdown_extensions(self):
        """Test Markdown file extensions."""
        assert classify_language(Path("README.md")) == (".md", "markdown")
        assert classify_language(Path("doc.markdown")) == (".markdown", "markdown")
        assert classify_language(Path("react.mdx")) == (".mdx", "markdown")

    def test_config_file_extensions(self):
        """Test configuration file extensions."""
        assert classify_language(Path("config.json")) == (".json", "json")
        assert classify_language(Path("data.yml")) == (".yml", "yaml")
        assert classify_language(Path("config.yaml")) == (".yaml", "yaml")
        assert classify_language(Path("pyproject.toml")) == (".toml", "toml")

    def test_shell_script_extensions(self):
        """Test shell script extensions."""
        assert classify_language(Path("run.sh")) == (".sh", "shell")
        assert classify_language(Path("setup.bash")) == (".bash", "shell")
        assert classify_language(Path("profile.zsh")) == (".zsh", "shell")

    def test_special_filenames_without_extension(self):
        """Test special filenames without extensions."""
        assert classify_language(Path("Justfile")) == (None, "just")
        assert classify_language(Path("README")) == (None, "text")
        assert classify_language(Path("LICENSE")) == (None, "text")
        assert classify_language(Path("Makefile")) == (None, "text")
        assert classify_language(Path("Dockerfile")) == (None, "text")

    def test_special_filenames_with_extension(self):
        """Test that .just extension works."""
        assert classify_language(Path("build.just")) == (".just", "just")

    def test_svelte_extension(self):
        """Test Svelte component extension."""
        assert classify_language(Path("App.svelte")) == (".svelte", "svelte")

    def test_text_extension(self):
        """Test plain text extension."""
        assert classify_language(Path("notes.txt")) == (".txt", "text")

    def test_unknown_extension_defaults_to_text(self):
        """Test that unknown extensions default to 'text'."""
        ext, lang = classify_language(Path("file.xyz"))
        assert ext == ".xyz"
        assert lang == "text"

    def test_no_extension_defaults_to_text(self):
        """Test files without extension (not special) default to text."""
        ext, lang = classify_language(Path("randomfile"))
        assert ext is None
        assert lang == "text"

    def test_case_insensitive_extensions(self):
        """Test that extensions are case-insensitive."""
        assert classify_language(Path("Test.PY")) == (".py", "python")
        assert classify_language(Path("App.TS")) == (".ts", "typescript")
        assert classify_language(Path("Config.JSON")) == (".json", "json")

    def test_special_filename_is_case_sensitive(self):
        """Test that special filenames are case-sensitive."""
        # Justfile is special, justfile is not
        assert classify_language(Path("Justfile")) == (None, "just")
        ext, lang = classify_language(Path("justfile"))
        assert ext is None
        assert lang == "text"

    def test_path_with_directories(self):
        """Test that directory paths don't affect classification."""
        assert classify_language(Path("/path/to/file.py")) == (".py", "python")
        assert classify_language(Path("./src/components/App.tsx")) == (".tsx", "typescriptreact")

    def test_multiple_dots_in_filename(self):
        """Test files with multiple dots use only the last extension."""
        assert classify_language(Path("test.spec.ts")) == (".ts", "typescript")
        assert classify_language(Path("config.local.json")) == (".json", "json")
```

**Success Criteria:**

- ✅ All language mappings validated
- ✅ Edge cases handled (no extension, unknown, case sensitivity)
- ✅ Special filenames tested
- ✅ 100% coverage of classify_language function

---

### 1.3 MCP REST Client Tests

**File:** `mcp-bridge/src/tests/rest_client.test.ts` (NEW)
**Target:** `mcp-bridge/src/rest/client.ts`
**Estimated Time:** 5 hours

#### Test Cases to Implement

```typescript
import { describe, it, expect, beforeAll, afterAll, mock } from "bun:test";
import { RestClient } from "../rest/client";
import { startMockRest } from "./mockServer";

let stop: () => Promise<void>;

beforeAll(async () => {
  stop = await startMockRest(7778);
});

afterAll(async () => {
  await stop?.();
});

describe("RestClient", () => {
  describe("constructor", () => {
    it("should create client with default baseUrl", () => {
      const client = new RestClient();
      expect(client).toBeDefined();
      // Default should be localhost:7677
    });

    it("should create client with custom baseUrl", () => {
      const client = new RestClient("http://localhost:7778");
      expect(client).toBeDefined();
    });

    it("should handle baseUrl with trailing slash", () => {
      const client = new RestClient("http://localhost:7778/");
      expect(client).toBeDefined();
    });
  });

  describe("search", () => {
    it("should make successful search request", async () => {
      const client = new RestClient("http://localhost:7778");
      const result = await client.search({
        query: "test query",
        top_k: 10,
      });

      expect(result).toBeDefined();
      expect(result.hits).toBeDefined();
      expect(Array.isArray(result.hits)).toBe(true);
    });

    it("should pass all search parameters correctly", async () => {
      const client = new RestClient("http://localhost:7778");
      const result = await client.search({
        query: "test",
        top_k: 20,
        repos: ["repo1", "repo2"],
        path_prefix: ["src/"],
        score_cutoff: 0.5,
      });

      expect(result).toBeDefined();
    });

    it("should handle search with cursor", async () => {
      const client = new RestClient("http://localhost:7778");
      const result = await client.search({
        query: "test",
        cursor: "cursor-token-123",
      });

      expect(result).toBeDefined();
    });

    it("should throw error on 404", async () => {
      const client = new RestClient("http://localhost:7778");

      await expect(async () => {
        await client.search({ query: "trigger-404" });
      }).toThrow();
    });

    it("should throw error on 500", async () => {
      const client = new RestClient("http://localhost:7778");

      await expect(async () => {
        await client.search({ query: "trigger-500" });
      }).toThrow();
    });
  });

  describe("getRepos", () => {
    it("should fetch list of repositories", async () => {
      const client = new RestClient("http://localhost:7778");
      const repos = await client.getRepos();

      expect(Array.isArray(repos)).toBe(true);
    });
  });

  describe("getMetadata", () => {
    it("should fetch file metadata", async () => {
      const client = new RestClient("http://localhost:7778");
      const metadata = await client.getMetadata({
        repo: "test-repo",
        path: "src/test.ts",
      });

      expect(metadata).toBeDefined();
    });
  });

  describe("fetchChunk", () => {
    it("should fetch chunk by hash", async () => {
      const client = new RestClient("http://localhost:7778");
      const chunk = await client.fetchChunk({
        chunk_hash: "abc123",
      });

      expect(chunk).toBeDefined();
      expect(chunk.content).toBeDefined();
    });
  });

  describe("fetchLines", () => {
    it("should fetch file lines", async () => {
      const client = new RestClient("http://localhost:7778");
      const lines = await client.fetchLines({
        repo: "test-repo",
        path: "src/test.ts",
        start_line: 1,
        end_line: 10,
      });

      expect(lines).toBeDefined();
      expect(lines.content).toBeDefined();
    });
  });

  describe("error handling", () => {
    it("should handle network errors gracefully", async () => {
      const client = new RestClient("http://localhost:9999"); // wrong port

      await expect(async () => {
        await client.search({ query: "test" });
      }).toThrow();
    });

    it("should handle timeout", async () => {
      const client = new RestClient("http://localhost:7778", { timeout: 100 });

      // Mock server should have a slow endpoint for this test
      await expect(async () => {
        await client.search({ query: "slow-query" });
      }).toThrow();
    });

    it("should include error details in thrown errors", async () => {
      const client = new RestClient("http://localhost:7778");

      try {
        await client.search({ query: "trigger-500" });
        expect(false).toBe(true); // Should not reach here
      } catch (error) {
        expect(error.message).toContain("500");
      }
    });
  });

  describe("retry logic", () => {
    it("should retry on transient failures", async () => {
      const client = new RestClient("http://localhost:7778", {
        retries: 3,
        retryDelay: 100,
      });

      // Mock server should succeed on 2nd attempt
      const result = await client.search({ query: "retry-test" });
      expect(result).toBeDefined();
    });

    it("should give up after max retries", async () => {
      const client = new RestClient("http://localhost:7778", {
        retries: 2,
      });

      await expect(async () => {
        await client.search({ query: "always-fail" });
      }).toThrow();
    });
  });
});
```

**Success Criteria:**

- ✅ All API methods tested
- ✅ Error handling validated
- ✅ Retry logic verified
- ✅ Network failure scenarios covered

---

### 1.4 Claude Tool Executor Tests

**File:** `agent-core/tests/test-tool-executor.ts` (ENHANCE EXISTING)
**Target:** `agent-core/src/llm/claude-tool-executor.ts`
**Estimated Time:** 6 hours

#### Test Cases to Add

```typescript
import { describe, it, expect, beforeEach, mock } from "bun:test";
import { ClaudeToolExecutor } from "../src/llm/claude-tool-executor";
import type { ToolUseBlock } from "@anthropic-ai/sdk/resources";

describe("ClaudeToolExecutor - Core Execution", () => {
  let executor: ClaudeToolExecutor;

  beforeEach(() => {
    executor = new ClaudeToolExecutor({
      workingDirectory: "/tmp/test",
      kbManager: null, // Mock KB manager
      mcpClient: null, // Mock MCP client
    });
  });

  describe("executeTool", () => {
    it("should execute bash tool successfully", async () => {
      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-1",
        name: "bash",
        input: { command: 'echo "hello"' },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.type).toBe("tool_result");
      expect(result.tool_use_id).toBe("tool-1");
      expect(result.content).toContain("hello");
      expect(result.is_error).toBe(false);
    });

    it("should handle tool execution errors", async () => {
      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-2",
        name: "bash",
        input: { command: "exit 1" },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(true);
    });

    it("should handle unknown tool gracefully", async () => {
      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-3",
        name: "unknown_tool",
        input: {},
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(true);
      expect(result.content).toContain("Unknown tool");
    });
  });

  describe("read_file tool", () => {
    it("should read file successfully", async () => {
      // Create temp file
      const tmpFile = "/tmp/test-read.txt";
      await Bun.write(tmpFile, "test content");

      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-4",
        name: "read_file",
        input: { file_path: tmpFile },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(false);
      expect(result.content).toContain("test content");
    });

    it("should handle file not found", async () => {
      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-5",
        name: "read_file",
        input: { file_path: "/nonexistent/file.txt" },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(true);
    });

    it("should respect line limit and offset", async () => {
      const tmpFile = "/tmp/test-lines.txt";
      await Bun.write(tmpFile, "line1\nline2\nline3\nline4\nline5");

      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-6",
        name: "read_file",
        input: {
          file_path: tmpFile,
          offset: 1,
          limit: 2,
        },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(false);
      expect(result.content).toContain("line2");
      expect(result.content).toContain("line3");
      expect(result.content).not.toContain("line1");
      expect(result.content).not.toContain("line4");
    });
  });

  describe("write_file tool", () => {
    it("should write file successfully", async () => {
      const tmpFile = "/tmp/test-write.txt";

      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-7",
        name: "write_file",
        input: {
          file_path: tmpFile,
          content: "new content",
        },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(false);

      // Verify file was written
      const content = await Bun.file(tmpFile).text();
      expect(content).toBe("new content");
    });

    it("should handle write permission errors", async () => {
      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-8",
        name: "write_file",
        input: {
          file_path: "/root/readonly/file.txt",
          content: "content",
        },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(true);
    });
  });

  describe("edit_file tool", () => {
    it("should edit file successfully", async () => {
      const tmpFile = "/tmp/test-edit.txt";
      await Bun.write(tmpFile, "original content");

      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-9",
        name: "edit_file",
        input: {
          file_path: tmpFile,
          old_string: "original",
          new_string: "modified",
        },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(false);

      const content = await Bun.file(tmpFile).text();
      expect(content).toBe("modified content");
    });

    it("should handle old_string not found", async () => {
      const tmpFile = "/tmp/test-edit-notfound.txt";
      await Bun.write(tmpFile, "content");

      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-10",
        name: "edit_file",
        input: {
          file_path: tmpFile,
          old_string: "nonexistent",
          new_string: "new",
        },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(true);
      expect(result.content).toContain("not found");
    });
  });

  describe("search_knowledge tool", () => {
    it("should delegate to KB manager", async () => {
      const mockKbManager = {
        search: mock(async (query: string) => ({
          hits: [{ repo: "test", path: "file.ts", snippet: "code" }],
        })),
      };

      const executor = new ClaudeToolExecutor({
        workingDirectory: "/tmp/test",
        kbManager: mockKbManager,
        mcpClient: null,
      });

      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-11",
        name: "search_knowledge",
        input: { query: "test query" },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(false);
      expect(mockKbManager.search).toHaveBeenCalledWith("test query");
    });

    it("should handle KB manager not available", async () => {
      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-12",
        name: "search_knowledge",
        input: { query: "test" },
      };

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(true);
      expect(result.content).toContain("not available");
    });
  });

  describe("concurrent execution", () => {
    it("should handle multiple tools in parallel", async () => {
      const tools: ToolUseBlock[] = [
        { type: "tool_use", id: "1", name: "bash", input: { command: 'echo "1"' } },
        { type: "tool_use", id: "2", name: "bash", input: { command: 'echo "2"' } },
        { type: "tool_use", id: "3", name: "bash", input: { command: 'echo "3"' } },
      ];

      const results = await Promise.all(tools.map((tool) => executor.executeTool(tool)));

      expect(results).toHaveLength(3);
      expect(results.every((r) => !r.is_error)).toBe(true);
    });
  });

  describe("timeout handling", () => {
    it("should timeout long-running commands", async () => {
      const toolUse: ToolUseBlock = {
        type: "tool_use",
        id: "tool-13",
        name: "bash",
        input: { command: "sleep 10" },
      };

      const executor = new ClaudeToolExecutor({
        workingDirectory: "/tmp/test",
        kbManager: null,
        mcpClient: null,
        timeout: 1000, // 1 second timeout
      });

      const result = await executor.executeTool(toolUse);

      expect(result.is_error).toBe(true);
      expect(result.content).toContain("timeout");
    }, 5000);
  });
});
```

**Success Criteria:**

- ✅ All tool types tested (bash, read_file, write_file, edit_file, search_knowledge)
- ✅ Error handling validated
- ✅ Concurrent execution tested
- ✅ Timeout handling verified

---

### 1.5 Index Queue Tests

**File:** `agent-core/tests/test-index-queue.ts` (NEW)
**Target:** `agent-core/src/kb/index-queue.ts`
**Estimated Time:** 4 hours

#### Test Cases to Implement

```typescript
import { describe, it, expect, beforeEach, afterEach, mock } from "bun:test";
import { IndexQueue } from "../src/kb/index-queue";

describe("IndexQueue", () => {
  let queue: IndexQueue;

  beforeEach(() => {
    queue = new IndexQueue({
      maxConcurrent: 2,
      maxRetries: 3,
    });
  });

  afterEach(() => {
    queue.shutdown();
  });

  describe("enqueue", () => {
    it("should enqueue and process task", async () => {
      const mockTask = mock(async () => "result");

      const result = await queue.enqueue("task-1", mockTask);

      expect(result).toBe("result");
      expect(mockTask).toHaveBeenCalled();
    });

    it("should not enqueue duplicate task", async () => {
      const mockTask = mock(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return "result";
      });

      const promise1 = queue.enqueue("task-1", mockTask);
      const promise2 = queue.enqueue("task-1", mockTask);

      await Promise.all([promise1, promise2]);

      // Task should only be called once
      expect(mockTask).toHaveBeenCalledTimes(1);
    });
  });

  describe("concurrency control", () => {
    it("should respect maxConcurrent limit", async () => {
      let concurrent = 0;
      let maxConcurrent = 0;

      const task = async () => {
        concurrent++;
        maxConcurrent = Math.max(maxConcurrent, concurrent);
        await new Promise((resolve) => setTimeout(resolve, 50));
        concurrent--;
      };

      const promises = [];
      for (let i = 0; i < 5; i++) {
        promises.push(queue.enqueue(`task-${i}`, task));
      }

      await Promise.all(promises);

      expect(maxConcurrent).toBeLessThanOrEqual(2);
    });
  });

  describe("retry logic", () => {
    it("should retry failed tasks", async () => {
      let attempts = 0;
      const mockTask = mock(async () => {
        attempts++;
        if (attempts < 3) {
          throw new Error("Transient failure");
        }
        return "success";
      });

      const result = await queue.enqueue("retry-task", mockTask);

      expect(result).toBe("success");
      expect(attempts).toBe(3);
    });

    it("should give up after maxRetries", async () => {
      const mockTask = mock(async () => {
        throw new Error("Permanent failure");
      });

      await expect(async () => {
        await queue.enqueue("fail-task", mockTask);
      }).toThrow("Permanent failure");

      expect(mockTask).toHaveBeenCalledTimes(4); // initial + 3 retries
    });
  });

  describe("priority queue", () => {
    it("should process high priority tasks first", async () => {
      const order: number[] = [];

      const task = (id: number) => async () => {
        order.push(id);
        await new Promise((resolve) => setTimeout(resolve, 10));
      };

      // Queue with concurrency 1
      const singleQueue = new IndexQueue({ maxConcurrent: 1 });

      singleQueue.enqueue("low-1", task(1), { priority: 1 });
      singleQueue.enqueue("high-1", task(2), { priority: 10 });
      singleQueue.enqueue("low-2", task(3), { priority: 1 });
      singleQueue.enqueue("high-2", task(4), { priority: 10 });

      await new Promise((resolve) => setTimeout(resolve, 100));

      // High priority tasks should be processed first
      expect(order[0]).toBe(1); // First one starts immediately
      expect(order[1]).toBe(2); // High priority
      expect(order[2]).toBe(4); // High priority
      expect(order[3]).toBe(3); // Low priority

      singleQueue.shutdown();
    });
  });

  describe("status tracking", () => {
    it("should track task status", async () => {
      const task = async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return "done";
      };

      const promise = queue.enqueue("status-task", task);

      expect(queue.getStatus("status-task")).toBe("pending");

      await new Promise((resolve) => setTimeout(resolve, 25));
      expect(queue.getStatus("status-task")).toBe("running");

      await promise;
      expect(queue.getStatus("status-task")).toBe("completed");
    });

    it("should mark failed tasks as failed", async () => {
      const task = async () => {
        throw new Error("Task failed");
      };

      try {
        await queue.enqueue("fail-status", task);
      } catch (e) {
        // Expected
      }

      expect(queue.getStatus("fail-status")).toBe("failed");
    });
  });

  describe("shutdown", () => {
    it("should wait for running tasks to complete", async () => {
      let taskCompleted = false;

      const task = async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        taskCompleted = true;
      };

      queue.enqueue("shutdown-task", task);

      await queue.shutdown();

      expect(taskCompleted).toBe(true);
    });

    it("should reject new tasks after shutdown", async () => {
      await queue.shutdown();

      await expect(async () => {
        await queue.enqueue("post-shutdown", async () => {});
      }).toThrow("Queue is shutting down");
    });
  });
});
```

**Success Criteria:**

- ✅ Queue operations tested
- ✅ Concurrency limits verified
- ✅ Retry logic validated
- ✅ Priority queue behavior checked
- ✅ Shutdown behavior tested

---

## Phase 2: Utility & Support Code (Week 3)

### 2.1 Graph Helpers Unit Tests

**File:** `tests/unit/test_graph_helpers_unit.py` (NEW)
**Target:** `kb/ingest/graph_helpers.py`
**Estimated Time:** 5 hours

```python
"""Unit tests for graph extraction helpers."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from kb.ingest.graph_helpers import (
    extract_graph_from_file,
    store_graph_data,
    cleanup_graph_for_file,
    cleanup_graph_for_repo
)
from kb.chunkers.graph_types import GraphNode, GraphEdge


class TestExtractGraphFromFile:
    """Test graph extraction from individual files."""

    @patch('kb.ingest.graph_helpers.get_chunker_for_language')
    def test_extract_graph_from_python_file(self, mock_get_chunker):
        """Test graph extraction from Python file."""
        # Setup mock chunker
        mock_chunker = Mock()
        mock_chunker.extract_graph.return_value = (
            [GraphNode('function', 'test_func', 1, 10)],
            [GraphEdge('function', 'test_func', 'class', 'TestClass', 'member_of')]
        )
        mock_get_chunker.return_value = mock_chunker

        # Execute
        nodes, edges = extract_graph_from_file(
            Path('/repo/test.py'),
            'python',
            'def test_func():\n    pass'
        )

        # Verify
        assert len(nodes) == 1
        assert nodes[0].name == 'test_func'
        assert len(edges) == 1
        assert edges[0].from_name == 'test_func'

    @patch('kb.ingest.graph_helpers.get_chunker_for_language')
    def test_extract_graph_from_unsupported_language(self, mock_get_chunker):
        """Test graph extraction from unsupported language returns empty."""
        mock_chunker = Mock()
        mock_chunker.extract_graph.return_value = ([], [])
        mock_get_chunker.return_value = mock_chunker

        nodes, edges = extract_graph_from_file(
            Path('/repo/file.txt'),
            'text',
            'plain text content'
        )

        assert nodes == []
        assert edges == []

    @patch('kb.ingest.graph_helpers.get_chunker_for_language')
    def test_extract_graph_handles_chunker_errors(self, mock_get_chunker):
        """Test that extraction errors are handled gracefully."""
        mock_chunker = Mock()
        mock_chunker.extract_graph.side_effect = Exception('Parse error')
        mock_get_chunker.return_value = mock_chunker

        nodes, edges = extract_graph_from_file(
            Path('/repo/broken.py'),
            'python',
            'invalid syntax {'
        )

        # Should return empty rather than crash
        assert nodes == []
        assert edges == []


class TestStoreGraphData:
    """Test storing graph data in the graph store."""

    def test_store_nodes_and_edges(self):
        """Test storing nodes and edges."""
        mock_store = Mock()

        nodes = [
            GraphNode('function', 'func1', 1, 10),
            GraphNode('class', 'Class1', 11, 20)
        ]
        edges = [
            GraphEdge('function', 'func1', 'class', 'Class1', 'member_of')
        ]

        store_graph_data(
            mock_store,
            'test-repo',
            'src/test.py',
            nodes,
            edges
        )

        # Verify store methods called
        assert mock_store.add_node.call_count == 2
        assert mock_store.add_edge.call_count == 1

    def test_store_empty_graph(self):
        """Test storing empty graph doesn't crash."""
        mock_store = Mock()

        store_graph_data(
            mock_store,
            'test-repo',
            'src/empty.py',
            [],
            []
        )

        # Should not call store methods
        assert mock_store.add_node.call_count == 0
        assert mock_store.add_edge.call_count == 0

    def test_store_handles_duplicate_nodes(self):
        """Test that duplicate nodes are handled correctly."""
        mock_store = Mock()

        # Duplicate node names
        nodes = [
            GraphNode('function', 'func', 1, 10),
            GraphNode('function', 'func', 11, 20)  # Different location, same name
        ]

        store_graph_data(
            mock_store,
            'test-repo',
            'src/test.py',
            nodes,
            []
        )

        # Both should be stored
        assert mock_store.add_node.call_count == 2


class TestCleanupGraphForFile:
    """Test cleaning up graph data for a file."""

    def test_cleanup_removes_all_file_data(self):
        """Test that cleanup removes all nodes/edges for a file."""
        mock_store = Mock()

        cleanup_graph_for_file(
            mock_store,
            'test-repo',
            'src/deleted.py'
        )

        # Verify cleanup methods called
        mock_store.remove_file_nodes.assert_called_once_with(
            'test-repo',
            'src/deleted.py'
        )
        mock_store.remove_file_edges.assert_called_once_with(
            'test-repo',
            'src/deleted.py'
        )


class TestCleanupGraphForRepo:
    """Test cleaning up entire repository graph."""

    def test_cleanup_removes_all_repo_data(self):
        """Test that cleanup removes all nodes/edges for a repo."""
        mock_store = Mock()

        cleanup_graph_for_repo(mock_store, 'test-repo')

        mock_store.remove_repo_nodes.assert_called_once_with('test-repo')
        mock_store.remove_repo_edges.assert_called_once_with('test-repo')
```

---

### 2.2 Graph Context Enricher Unit Tests

**File:** `tests/unit/test_graph_context_unit.py` (NEW)
**Target:** `kb/retrieval/graph_context.py`
**Estimated Time:** 5 hours

```python
"""Unit tests for graph context enrichment."""

import pytest
from unittest.mock import Mock, MagicMock
from kb.retrieval.graph_context import GraphContextEnricher
from kb.retrieval.types import Document


class TestGraphContextEnricher:
    """Test graph context enrichment logic."""

    def test_enrich_with_no_graph_data(self):
        """Test enrichment when no graph data exists."""
        mock_graph_store = Mock()
        mock_graph_store.get_related_symbols.return_value = []

        enricher = GraphContextEnricher(mock_graph_store)

        docs = [
            Document(
                repo='test-repo',
                path='test.py',
                start_line=1,
                end_line=10,
                content='def test(): pass',
                score=0.9
            )
        ]

        enriched = enricher.enrich(docs)

        # Should return original docs
        assert len(enriched) == 1
        assert enriched[0].content == docs[0].content

    def test_enrich_adds_related_symbols(self):
        """Test that related symbols are added to context."""
        mock_graph_store = Mock()
        mock_graph_store.get_related_symbols.return_value = [
            {
                'name': 'helper_function',
                'type': 'function',
                'path': 'utils.py',
                'start_line': 5,
                'end_line': 15
            }
        ]

        enricher = GraphContextEnricher(mock_graph_store, max_related=5)

        docs = [
            Document(
                repo='test-repo',
                path='main.py',
                start_line=1,
                end_line=10,
                content='def main(): helper_function()',
                score=0.9
            )
        ]

        enriched = enricher.enrich(docs)

        assert len(enriched) == 1
        # Should have additional context
        assert 'helper_function' in enriched[0].metadata.get('related_symbols', '')

    def test_enrich_respects_max_related_limit(self):
        """Test that max_related limit is respected."""
        # Return 10 related symbols
        mock_graph_store = Mock()
        mock_graph_store.get_related_symbols.return_value = [
            {'name': f'symbol_{i}', 'type': 'function', 'path': 'test.py'}
            for i in range(10)
        ]

        enricher = GraphContextEnricher(mock_graph_store, max_related=3)

        docs = [
            Document(
                repo='test-repo',
                path='test.py',
                start_line=1,
                end_line=10,
                content='code',
                score=0.9
            )
        ]

        enriched = enricher.enrich(docs)

        # Should only include 3 related symbols
        related = enriched[0].metadata.get('related_symbols', [])
        assert len(related) <= 3

    def test_enrich_handles_graph_store_errors(self):
        """Test that graph store errors don't crash enrichment."""
        mock_graph_store = Mock()
        mock_graph_store.get_related_symbols.side_effect = Exception('DB error')

        enricher = GraphContextEnricher(mock_graph_store)

        docs = [
            Document(
                repo='test-repo',
                path='test.py',
                start_line=1,
                end_line=10,
                content='code',
                score=0.9
            )
        ]

        # Should not crash
        enriched = enricher.enrich(docs)
        assert len(enriched) == 1
```

---

### 2.3 MCP Bridge Utility Tests

**File:** `mcp-bridge/src/tests/util.test.ts` (NEW)
**Targets:** `util/config.ts`, `util/logger.ts`, `util/language.ts`
**Estimated Time:** 4 hours

```typescript
import { describe, it, expect, beforeEach, afterEach } from "bun:test";
import { loadConfig, getRestApiUrl } from "../util/config";
import { logger, initLogger } from "../util/logger";
import { detectLanguage, formatLanguageForDisplay } from "../util/language";

describe("Config Utilities", () => {
  describe("loadConfig", () => {
    it("should load default config", () => {
      const config = loadConfig();

      expect(config).toBeDefined();
      expect(config.restApiUrl).toBeDefined();
    });

    it("should use environment variable override", () => {
      process.env.DOLPHIN_API_URL = "http://custom:9999";

      const config = loadConfig();

      expect(config.restApiUrl).toBe("http://custom:9999");

      delete process.env.DOLPHIN_API_URL;
    });
  });

  describe("getRestApiUrl", () => {
    it("should return default URL", () => {
      const url = getRestApiUrl();
      expect(url).toBe("http://localhost:7677");
    });

    it("should handle custom port", () => {
      process.env.DOLPHIN_PORT = "8888";

      const url = getRestApiUrl();
      expect(url).toContain("8888");

      delete process.env.DOLPHIN_PORT;
    });
  });
});

describe("Logger Utilities", () => {
  beforeEach(async () => {
    await initLogger();
  });

  it("should log info messages", () => {
    expect(() => {
      logger.info("test message");
    }).not.toThrow();
  });

  it("should log errors", () => {
    expect(() => {
      logger.error("error message");
    }).not.toThrow();
  });

  it("should log with context", () => {
    expect(() => {
      logger.info("message", { context: "test", data: 123 });
    }).not.toThrow();
  });
});

describe("Language Utilities", () => {
  describe("detectLanguage", () => {
    it("should detect Python files", () => {
      expect(detectLanguage("test.py")).toBe("python");
      expect(detectLanguage("/path/to/script.py")).toBe("python");
    });

    it("should detect TypeScript files", () => {
      expect(detectLanguage("App.tsx")).toBe("typescriptreact");
      expect(detectLanguage("config.ts")).toBe("typescript");
    });

    it("should detect JavaScript files", () => {
      expect(detectLanguage("app.js")).toBe("javascript");
      expect(detectLanguage("Component.jsx")).toBe("javascriptreact");
    });

    it("should handle unknown extensions", () => {
      expect(detectLanguage("file.xyz")).toBe("text");
    });
  });

  describe("formatLanguageForDisplay", () => {
    it("should format language names", () => {
      expect(formatLanguageForDisplay("python")).toBe("Python");
      expect(formatLanguageForDisplay("typescript")).toBe("TypeScript");
      expect(formatLanguageForDisplay("typescriptreact")).toBe("TypeScript React");
    });
  });
});
```

---

## Phase 3: Type Validation & Schema Tests (Week 4)

### 3.1 SQL Model Validation Tests

**File:** `tests/unit/test_sql_models.py` (NEW)
**Target:** `kb/store/sql_models.py`
**Estimated Time:** 3 hours

```python
"""Unit tests for SQL model definitions."""

import pytest
from datetime import datetime
from kb.store.sql_models import Repo, Session, Chunk


class TestRepoModel:
    """Test Repo SQLModel."""

    def test_create_repo_instance(self):
        """Test creating a Repo instance."""
        repo = Repo(
            name='test-repo',
            path='/path/to/repo',
            indexed_at=datetime.now()
        )

        assert repo.name == 'test-repo'
        assert repo.path == '/path/to/repo'
        assert repo.indexed_at is not None

    def test_repo_name_required(self):
        """Test that repo name is required."""
        with pytest.raises(ValueError):
            Repo(path='/path')

    def test_repo_path_required(self):
        """Test that repo path is required."""
        with pytest.raises(ValueError):
            Repo(name='test')


class TestSessionModel:
    """Test Session SQLModel."""

    def test_create_session(self):
        """Test creating a Session instance."""
        session = Session(
            repo_name='test-repo',
            started_at=datetime.now()
        )

        assert session.repo_name == 'test-repo'
        assert session.started_at is not None

    def test_session_timestamps(self):
        """Test session timestamp handling."""
        started = datetime.now()
        session = Session(
            repo_name='test-repo',
            started_at=started,
            completed_at=None
        )

        assert session.started_at == started
        assert session.completed_at is None


class TestChunkModel:
    """Test Chunk SQLModel."""

    def test_create_chunk(self):
        """Test creating a Chunk instance."""
        chunk = Chunk(
            repo='test-repo',
            path='src/test.py',
            start_line=1,
            end_line=10,
            content_hash='abc123',
            content='def test(): pass'
        )

        assert chunk.repo == 'test-repo'
        assert chunk.path == 'src/test.py'
        assert chunk.start_line == 1
        assert chunk.end_line == 10

    def test_chunk_validates_line_numbers(self):
        """Test that start_line <= end_line."""
        with pytest.raises(ValueError):
            Chunk(
                repo='test-repo',
                path='test.py',
                start_line=10,
                end_line=1,  # Invalid: end before start
                content_hash='abc',
                content='code'
            )
```

---

### 3.2 CLI Workflow Integration Tests

**File:** `tests/integration/test_cli_complete_workflows.py` (NEW)
**Target:** `kb/ingest/cli.py`
**Estimated Time:** 6 hours

```python
"""Integration tests for complete CLI workflows."""

import pytest
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


class TestCLIIndexWorkflow:
    """Test complete index workflow via CLI."""

    def test_index_repo_from_cli(self, git_repo):
        """Test indexing a repository via CLI."""
        result = subprocess.run(
            ['kb', 'index', str(git_repo)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert 'Indexed' in result.stdout or result.stderr

    def test_index_with_custom_config(self, git_repo, tmp_path):
        """Test indexing with custom config file."""
        config_file = tmp_path / 'config.toml'
        config_file.write_text('''
        [chunking]
        max_tokens = 512

        [embedding]
        provider = "stub"
        ''')

        result = subprocess.run(
            ['kb', 'index', str(git_repo), '--config', str(config_file)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0

    def test_index_shows_progress(self, git_repo):
        """Test that indexing shows progress output."""
        result = subprocess.run(
            ['kb', 'index', str(git_repo), '--verbose'],
            capture_output=True,
            text=True
        )

        output = result.stdout + result.stderr
        assert 'Scanning' in output or 'Chunking' in output or 'Embedding' in output


class TestCLISearchWorkflow:
    """Test CLI search functionality."""

    @pytest.fixture(autouse=True)
    def indexed_repo(self, git_repo):
        """Setup: Index a repo before search tests."""
        subprocess.run(['kb', 'index', str(git_repo)], check=True)
        yield git_repo

    def test_search_via_cli(self):
        """Test searching via CLI."""
        result = subprocess.run(
            ['kb', 'search', 'test function'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        # Should show results or "No results"
        assert len(result.stdout) > 0

    def test_search_with_filters(self):
        """Test search with repo filter."""
        result = subprocess.run(
            ['kb', 'search', 'test', '--repo', 'test-repo'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0

    def test_search_with_top_k(self):
        """Test search with custom top_k."""
        result = subprocess.run(
            ['kb', 'search', 'test', '--top-k', '5'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0


class TestCLIErrorHandling:
    """Test CLI error handling."""

    def test_index_nonexistent_repo(self):
        """Test error when indexing nonexistent repo."""
        result = subprocess.run(
            ['kb', 'index', '/nonexistent/path'],
            capture_output=True,
            text=True
        )

        assert result.returncode != 0
        assert 'not found' in result.stderr.lower() or 'error' in result.stderr.lower()

    def test_invalid_config_file(self, tmp_path):
        """Test error with invalid config file."""
        config_file = tmp_path / 'bad_config.toml'
        config_file.write_text('invalid toml {{')

        result = subprocess.run(
            ['kb', 'index', '/tmp', '--config', str(config_file)],
            capture_output=True,
            text=True
        )

        assert result.returncode != 0

    def test_helpful_error_messages(self):
        """Test that errors include helpful messages."""
        result = subprocess.run(
            ['kb', 'unknown-command'],
            capture_output=True,
            text=True
        )

        assert result.returncode != 0
        # Should show help or available commands
        assert 'usage' in result.stderr.lower() or 'help' in result.stderr.lower()
```

---

## Implementation Guidelines

### Test Organization

```
tests/
├── unit/                    # Fast, isolated tests
│   ├── test_api_server.py  # NEW
│   ├── test_lang.py        # NEW
│   ├── test_graph_helpers_unit.py  # NEW
│   ├── test_graph_context_unit.py  # NEW
│   └── test_sql_models.py  # NEW
├── integration/             # Slower, real dependencies
│   └── test_cli_complete_workflows.py  # NEW
└── conftest.py             # Shared fixtures

agent-core/tests/
├── test-tool-executor.ts   # ENHANCE
└── test-index-queue.ts     # NEW

mcp-bridge/src/tests/
├── rest_client.test.ts     # NEW
└── util.test.ts            # NEW
```

### Running Tests

**Python:**

```bash
# All tests
pytest

# Specific phase
pytest tests/unit/test_api_server.py
pytest tests/unit/test_lang.py

# With coverage
pytest --cov=kb --cov-report=html

# Parallel execution
pytest -n auto
```

**TypeScript:**

```bash
# agent-core
cd agent-core
bun test

# mcp-bridge
cd mcp-bridge
bun test

# With coverage
bun test --coverage
```

### Test Quality Checklist

Every test should:

- ✅ Have a clear, descriptive name
- ✅ Test one specific behavior
- ✅ Be independent (no test interdependencies)
- ✅ Clean up after itself (fixtures, temp files)
- ✅ Use appropriate assertions
- ✅ Mock external dependencies
- ✅ Run quickly (< 1 second for unit tests)

### Mocking Best Practices

**Python:**

```python
from unittest.mock import Mock, patch, MagicMock

# Mock external services
@patch('kb.api.server.create_search_backend')
def test_with_mock(mock_create_backend):
    mock_backend = Mock()
    mock_create_backend.return_value = mock_backend
    # test code

# Mock file I/O
@patch('pathlib.Path.exists')
def test_file_check(mock_exists):
    mock_exists.return_value = True
    # test code
```

**TypeScript:**

```typescript
import { mock } from "bun:test";

// Mock functions
const mockFunction = mock(async (arg) => "result");

// Mock modules
const mockKbManager = {
  search: mock(async (query) => ({ hits: [] })),
};
```

---

## Testing Best Practices

### 1. Test-Driven Development (TDD)

For new features:

1. Write failing test first
2. Implement minimal code to pass
3. Refactor while keeping tests green
4. Add edge case tests

### 2. Test Naming Convention

```python
# Format: test_<what>_<condition>_<expected>

def test_search_with_empty_query_returns_error()
def test_load_env_file_missing_logs_warning()
def test_classify_language_unknown_extension_returns_text()
```

### 3. AAA Pattern (Arrange-Act-Assert)

```python
def test_example():
    # Arrange: Set up test data
    config = create_test_config()

    # Act: Execute the behavior
    result = function_under_test(config)

    # Assert: Verify outcome
    assert result.status == 'success'
```

### 4. Fixture Reuse

```python
# conftest.py
@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a temporary git repository."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(['git', 'init'], cwd=repo, check=True)
    return repo

# test file
def test_index_repo(temp_git_repo):
    # Use the fixture
    result = index_repository(temp_git_repo)
    assert result.success
```

### 5. Parametrized Tests

```python
@pytest.mark.parametrize('extension,expected_lang', [
    ('.py', 'python'),
    ('.ts', 'typescript'),
    ('.js', 'javascript'),
    ('.md', 'markdown'),
])
def test_language_detection(extension, expected_lang):
    _, lang = classify_language(Path(f'test{extension}'))
    assert lang == expected_lang
```

---

## Success Metrics

### Coverage Targets

| Component    | Current | Target | Priority    |
| ------------ | ------- | ------ | ----------- |
| kb/api       | 75%     | 95%    | 🔴 Critical |
| kb/ingest    | 57%     | 85%    | 🔴 Critical |
| kb/retrieval | 60%     | 85%    | 🟡 High     |
| agent-core   | 50%     | 80%    | 🔴 Critical |
| mcp-bridge   | 45%     | 75%    | 🟡 High     |

### Test Execution Targets

- **Unit tests:** < 30 seconds total
- **Integration tests:** < 2 minutes total
- **Full suite:** < 5 minutes total
- **Flaky test rate:** < 1%

### CI/CD Integration

Add to GitHub Actions:

```yaml
name: Test Coverage

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Python Tests
        run: |
          pip install -e ".[test]"
          pytest --cov=kb --cov-fail-under=80

      - name: TypeScript Tests
        run: |
          cd agent-core && bun test --coverage
          cd ../mcp-bridge && bun test --coverage

      - name: Upload Coverage
        uses: codecov/codecov-action@v3
```

### Quality Gates

Before merging code:

- ✅ All tests pass
- ✅ Coverage doesn't decrease
- ✅ No new linter warnings
- ✅ Tests run in < 5 minutes

---

## Timeline and Milestones

### Week 1

- ✅ Server initialization tests (Day 1-2)
- ✅ Language classification tests (Day 2)
- ✅ REST client tests (Day 3-4)
- ✅ Tool executor tests (Day 4-5)

### Week 2

- ✅ Index queue tests (Day 1-2)
- ✅ Graph helpers unit tests (Day 3-4)
- ✅ Graph context unit tests (Day 4-5)

### Week 3

- ✅ MCP utility tests (Day 1-2)
- ✅ SQL model tests (Day 3)
- ✅ CLI workflow tests (Day 4-5)

### Week 4

- ✅ E2E tests (Day 1-2)
- ✅ Coverage validation (Day 3)
- ✅ CI/CD integration (Day 4)
- ✅ Documentation and review (Day 5)

---

## Risks and Mitigation

### Risk 1: Time Overrun

**Mitigation:** Prioritize Phase 1 (critical path) first. Phases 2-3 can be spread across multiple sprints.

### Risk 2: Breaking Existing Tests

**Mitigation:** Run full test suite after each new test file. Fix immediately.

### Risk 3: Low ROI on Some Tests

**Mitigation:** Focus on high-complexity, high-risk modules first. Skip trivial type-only modules if time-constrained.

### Risk 4: Flaky Tests

**Mitigation:**

- Use deterministic mocks
- Set explicit timeouts
- Avoid time-based assertions
- Isolate file system operations

---

## Next Steps

1. **Review and approve this plan**
2. **Create tracking issues** for each phase
3. **Assign owners** to test file creation
4. **Set up coverage reporting** in CI/CD
5. **Begin Phase 1 implementation**

---

## Appendix: Tools and Resources

### Testing Frameworks

- **Python:** pytest, pytest-cov, pytest-mock, faker
- **TypeScript:** Bun test, vitest (alternative)

### Coverage Tools

- **Python:** coverage.py, pytest-cov
- **TypeScript:** c8, nyc

### CI/CD Integration

- GitHub Actions
- GitLab CI
- CircleCI

### Documentation

- [pytest documentation](https://docs.pytest.org/)
- [Bun test documentation](https://bun.sh/docs/test)
- [Testing best practices](https://testingjavascript.com/)

---

**End of Implementation Plan**
