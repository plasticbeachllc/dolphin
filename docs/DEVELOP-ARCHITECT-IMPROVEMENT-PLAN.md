# Develop-Architect Branch: Improvement Plan & Specifications

**Version:** 1.1
**Date:** 2025-11-12
**Branch:** develop-architect
**Status:** In Progress

**Changelog:**
- v1.1: Updated WP1 with comprehensive file operation audit, simplified WP2 (no backward compatibility needed), added CI/CD to WP6
- v1.0: Initial specification

## Executive Summary

This document provides actionable specifications for addressing architectural, code quality, precision, and efficiency issues identified in the develop-architect branch code review. Issues are prioritized by impact and grouped into implementable work packages.

**Total Issues:** 24 across 5 categories
**Estimated Effort:** ~2-3 weeks (1 senior engineer) - simplified from 4 weeks
**Risk Level:** Low (no backward compatibility, comprehensive test coverage)

---

## Table of Contents

1. [Work Package Priorities](#work-package-priorities)
2. [Critical Security Fixes](#wp1-critical-security-fixes)
3. [Architecture Refactoring](#wp2-architecture-refactoring)
4. [Code Quality Improvements](#wp3-code-quality-improvements)
5. [Precision Enhancements](#wp4-precision-enhancements)
6. [Performance Optimization](#wp5-performance-optimization)
7. [Style & Consistency + CI/CD](#wp6-style--consistency--cicd)
8. [Implementation Timeline](#implementation-timeline)
9. [Testing Requirements](#testing-requirements)

---

## Work Package Priorities

### Priority Matrix

| Priority | Work Package | Complexity | Impact | Risk |
|----------|-------------|------------|--------|------|
| P0 | WP1: Critical Security Fixes | Low | Critical | Low |
| P1 | WP3: Code Quality (Error Handling) | Medium | High | Low |
| P1 | WP4: Precision Enhancements | Medium | High | Low |
| P2 | WP2: Architecture Refactoring | Medium | High | Low |
| P2 | WP5: Performance Optimization | Medium | Medium | Low |
| P3 | WP6: Style & CI/CD | Low | Medium | Low |

**Execution Order:**
1. WP1 (Security) - Immediate (Days 1-3)
2. WP3 (Error Handling) - Days 4-6
3. WP4 (Precision) - Days 7-9
4. WP5 (Performance) - Days 10-11
5. WP2 (Architecture) - Days 12-14
6. WP6 (Style & CI/CD) - Days 15-16

---

## WP1: Critical Security Fixes

### Issue 1.1: Universal Path Traversal Protection

**Problem:** Path validation only exists in StateStore, not applied comprehensively to all file operations.

**Current State - Comprehensive Audit:**

#### TypeScript/JavaScript File Operations:
✅ **Already Has Validation:**
- `mcp-bridge/src/tools/file-write.ts` (lines 23-42) - workspace boundary check
- `mcp-bridge/src/tools/read-files.ts` (lines 39-42) - workspace check
- `agent-core-v2/src/state/state-store.ts` (lines 513-524) - path validation helper

❌ **Needs Validation:**
- `agent-core/src/storage/toml-writer.ts` - NO validation, accepts any filepath
- `agent-core/src/kb/manager.ts` - potential file operations
- `agent-core/src/llm/diff-generator.ts` - file write operations
- `vscode-extension/src/views/provider.ts` - may handle file paths
- `vscode-extension/src/editor/diff-handler.ts` - file operations
- `agent-core-v2/src/context/context-builder.ts` - may read files

#### Python File Operations:
❌ **Needs Validation:**
- `kb/api/app.py:654` - `file_path.read_text()` - NO validation
- `kb/config.py:34,51` - template file read/write - NO validation
- `kb/store/sqlite_meta.py:1183` - `full_path.read_text()` - NO validation
- `kb/chunkers/registry.py:105-106` - template read/write - NO validation
- All `kb/ingest/` pipeline operations
- Any script in `scripts/` directory

**Risk Assessment:**
- **High Risk:** `agent-core/src/storage/toml-writer.ts` (accepts user-controlled paths)
- **High Risk:** `kb/api/app.py:654` (reads arbitrary file paths)
- **Medium Risk:** Config/template operations (typically internal paths)
- **Low Risk:** State store operations (already validated)

---

**Specification:**

#### 1.1.1 Create Shared Path Validation Module

**File:** `shared/security/path-validator.ts`

```typescript
/**
 * Security-hardened path validation for all file system operations.
 * Prevents path traversal attacks and validates file access.
 */

import { resolve, relative, normalize } from 'path';
import { existsSync, statSync, lstatSync } from 'fs';

export interface PathValidationOptions {
  /** Base directory that paths must be relative to */
  baseDir: string;

  /** Whether symlinks are allowed */
  allowSymlinks?: boolean;

  /** Whether to check if path exists */
  mustExist?: boolean;

  /** Allowed file extensions (e.g., ['.ts', '.js']). Empty = all allowed */
  allowedExtensions?: string[];

  /** Disallowed patterns (glob-style, e.g., '**/node_modules/**') */
  disallowedPatterns?: string[];
}

export class PathValidationError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly attemptedPath: string
  ) {
    super(message);
    this.name = 'PathValidationError';
  }
}

export class PathValidator {
  /**
   * Validate and resolve a file path against security constraints.
   *
   * @throws {PathValidationError} If path fails validation
   * @returns Absolute resolved path
   */
  static validate(path: string, options: PathValidationOptions): string {
    const { baseDir, allowSymlinks = false, mustExist = false } = options;

    // Reject absolute paths that don't start with baseDir
    if (path.startsWith('/') && !path.startsWith(baseDir)) {
      throw new PathValidationError(
        `Absolute path outside base directory: ${path}`,
        'PATH_TRAVERSAL',
        path
      );
    }

    // Normalize and resolve paths
    const normalizedPath = normalize(path);
    const resolvedPath = resolve(baseDir, normalizedPath);
    const resolvedBase = resolve(baseDir);

    // Check for path traversal
    const relativePath = relative(resolvedBase, resolvedPath);

    if (relativePath.startsWith('..') || resolve(resolvedBase, relativePath) !== resolvedPath) {
      throw new PathValidationError(
        `Path traversal detected: ${path} escapes base directory ${baseDir}`,
        'PATH_TRAVERSAL',
        path
      );
    }

    // Check if path exists (if required)
    if (mustExist && !existsSync(resolvedPath)) {
      throw new PathValidationError(
        `Path does not exist: ${path}`,
        'PATH_NOT_FOUND',
        path
      );
    }

    // Check symlinks (use lstat to detect symlinks before resolution)
    if (!allowSymlinks && existsSync(resolvedPath)) {
      const stats = lstatSync(resolvedPath);
      if (stats.isSymbolicLink()) {
        throw new PathValidationError(
          `Symbolic links not allowed: ${path}`,
          'SYMLINK_DISALLOWED',
          path
        );
      }
    }

    // Check file extensions
    if (options.allowedExtensions && options.allowedExtensions.length > 0) {
      const ext = normalizedPath.substring(normalizedPath.lastIndexOf('.'));
      if (!options.allowedExtensions.includes(ext)) {
        throw new PathValidationError(
          `File extension ${ext} not allowed. Allowed: ${options.allowedExtensions.join(', ')}`,
          'INVALID_EXTENSION',
          path
        );
      }
    }

    // Check disallowed patterns
    if (options.disallowedPatterns) {
      const minimatch = require('minimatch');
      for (const pattern of options.disallowedPatterns) {
        if (minimatch.minimatch(relativePath, pattern)) {
          throw new PathValidationError(
            `Path matches disallowed pattern ${pattern}: ${path}`,
            'PATTERN_DISALLOWED',
            path
          );
        }
      }
    }

    return resolvedPath;
  }

  /**
   * Validate multiple paths in batch.
   * Returns validated paths or throws on first error.
   */
  static validateBatch(paths: string[], options: PathValidationOptions): string[] {
    return paths.map(p => this.validate(p, options));
  }

  /**
   * Check if a path is safe without throwing.
   * Returns { valid: boolean, error?: string, resolvedPath?: string }
   */
  static check(path: string, options: PathValidationOptions): {
    valid: boolean;
    error?: string;
    resolvedPath?: string;
  } {
    try {
      const resolvedPath = this.validate(path, options);
      return { valid: true, resolvedPath };
    } catch (err) {
      return {
        valid: false,
        error: err instanceof Error ? err.message : String(err)
      };
    }
  }
}
```

**Tests:** `shared/security/__tests__/path-validator.test.ts`

```typescript
import { PathValidator, PathValidationError } from '../path-validator';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

describe('PathValidator', () => {
  const baseDir = '/home/user/project';

  describe('Path Traversal Protection', () => {
    it('should reject .. traversal', () => {
      expect(() =>
        PathValidator.validate('../etc/passwd', { baseDir })
      ).toThrow(PathValidationError);
    });

    it('should reject absolute paths outside base', () => {
      expect(() =>
        PathValidator.validate('/etc/passwd', { baseDir })
      ).toThrow(PathValidationError);
    });

    it('should reject URL-encoded traversal', () => {
      expect(() =>
        PathValidator.validate('%2e%2e/etc/passwd', { baseDir })
      ).toThrow(PathValidationError);
    });

    it('should reject double-encoded traversal', () => {
      expect(() =>
        PathValidator.validate('..%252F..%252Fetc/passwd', { baseDir })
      ).toThrow(PathValidationError);
    });

    it('should accept valid relative paths', () => {
      const result = PathValidator.validate('src/index.ts', { baseDir });
      expect(result).toBe('/home/user/project/src/index.ts');
    });

    it('should accept paths with dots in filename', () => {
      const result = PathValidator.validate('src/file.test.ts', { baseDir });
      expect(result).toBe('/home/user/project/src/file.test.ts');
    });
  });

  describe('Symlink Protection', () => {
    let tempDir: string;
    let symlinkPath: string;

    beforeEach(() => {
      tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'test-'));
      symlinkPath = path.join(tempDir, 'test-symlink');
      fs.symlinkSync('/etc/passwd', symlinkPath);
    });

    afterEach(() => {
      fs.unlinkSync(symlinkPath);
      fs.rmdirSync(tempDir);
    });

    it('should reject symlinks when disallowed', () => {
      const relativePath = path.relative(tempDir, symlinkPath);
      expect(() =>
        PathValidator.validate(relativePath, { baseDir: tempDir, allowSymlinks: false })
      ).toThrow(PathValidationError);
    });

    it('should allow symlinks when explicitly enabled', () => {
      const relativePath = path.relative(tempDir, symlinkPath);
      const result = PathValidator.validate(relativePath, {
        baseDir: tempDir,
        allowSymlinks: true
      });
      expect(result).toBeDefined();
    });
  });

  describe('Extension Filtering', () => {
    it('should reject disallowed extensions', () => {
      expect(() =>
        PathValidator.validate('malicious.exe', {
          baseDir,
          allowedExtensions: ['.ts', '.js', '.json']
        })
      ).toThrow(PathValidationError);
    });

    it('should allow whitelisted extensions', () => {
      const result = PathValidator.validate('src/index.ts', {
        baseDir,
        allowedExtensions: ['.ts', '.js', '.json']
      });
      expect(result).toBe('/home/user/project/src/index.ts');
    });
  });

  describe('Pattern Filtering', () => {
    it('should reject disallowed patterns', () => {
      expect(() =>
        PathValidator.validate('node_modules/evil/index.js', {
          baseDir,
          disallowedPatterns: ['**/node_modules/**']
        })
      ).toThrow(PathValidationError);
    });

    it('should allow paths not matching patterns', () => {
      const result = PathValidator.validate('src/index.ts', {
        baseDir,
        disallowedPatterns: ['**/node_modules/**']
      });
      expect(result).toBe('/home/user/project/src/index.ts');
    });
  });

  describe('Batch Validation', () => {
    it('should validate multiple paths successfully', () => {
      const paths = ['src/a.ts', 'src/b.ts', 'lib/c.js'];
      const results = PathValidator.validateBatch(paths, { baseDir });
      expect(results).toHaveLength(3);
      expect(results[0]).toContain('/project/src/a.ts');
    });

    it('should throw on first invalid path in batch', () => {
      const paths = ['src/a.ts', '../etc/passwd', 'src/b.ts'];
      expect(() =>
        PathValidator.validateBatch(paths, { baseDir })
      ).toThrow(PathValidationError);
    });
  });

  describe('Safe Check Method', () => {
    it('should return valid=true for safe paths', () => {
      const result = PathValidator.check('src/index.ts', { baseDir });
      expect(result.valid).toBe(true);
      expect(result.resolvedPath).toBeDefined();
    });

    it('should return valid=false for unsafe paths', () => {
      const result = PathValidator.check('../etc/passwd', { baseDir });
      expect(result.valid).toBe(false);
      expect(result.error).toContain('Path traversal');
    });
  });
});
```

#### 1.1.2 Python Path Validator

**File:** `kb/security/path_validator.py`

```python
"""Path validation for secure file operations."""

from pathlib import Path
from typing import List, Optional
import os


class PathValidationError(Exception):
    """Raised when path validation fails."""
    def __init__(self, message: str, code: str, attempted_path: str):
        super().__init__(message)
        self.code = code
        self.attempted_path = attempted_path


class PathValidator:
    """Validates file paths against security constraints."""

    @staticmethod
    def validate(
        path: str | Path,
        base_dir: str | Path,
        allow_symlinks: bool = False,
        must_exist: bool = False,
        allowed_extensions: Optional[List[str]] = None,
        disallowed_patterns: Optional[List[str]] = None
    ) -> Path:
        """Validate and resolve a file path.

        Args:
            path: Path to validate
            base_dir: Base directory that path must be relative to
            allow_symlinks: Whether symlinks are allowed
            must_exist: Whether path must exist
            allowed_extensions: Allowed file extensions (e.g., ['.py', '.toml'])
            disallowed_patterns: Disallowed glob patterns

        Returns:
            Resolved absolute Path object

        Raises:
            PathValidationError: If validation fails
        """
        # Convert to Path objects and resolve
        path_obj = Path(path)
        base = Path(base_dir).resolve()

        # Reject absolute paths outside base
        if path_obj.is_absolute() and not str(path_obj).startswith(str(base)):
            raise PathValidationError(
                f"Absolute path outside base directory: {path}",
                "PATH_TRAVERSAL",
                str(path)
            )

        # Resolve relative to base
        resolved = (base / path_obj).resolve()

        # Check path traversal
        try:
            resolved.relative_to(base)
        except ValueError:
            raise PathValidationError(
                f"Path traversal detected: {path} escapes base directory {base}",
                "PATH_TRAVERSAL",
                str(path)
            )

        # Check existence
        if must_exist and not resolved.exists():
            raise PathValidationError(
                f"Path does not exist: {path}",
                "PATH_NOT_FOUND",
                str(path)
            )

        # Check symlinks (before resolution to detect the link itself)
        if not allow_symlinks and resolved.exists():
            # Check each component of the path for symlinks
            current = resolved
            while current != base:
                if current.is_symlink():
                    raise PathValidationError(
                        f"Symbolic links not allowed: {path}",
                        "SYMLINK_DISALLOWED",
                        str(path)
                    )
                current = current.parent
                if current == current.parent:  # Root reached
                    break

        # Check extensions
        if allowed_extensions and resolved.suffix not in allowed_extensions:
            raise PathValidationError(
                f"File extension {resolved.suffix} not allowed. Allowed: {allowed_extensions}",
                "INVALID_EXTENSION",
                str(path)
            )

        # Check patterns
        if disallowed_patterns:
            from fnmatch import fnmatch
            rel_path = str(resolved.relative_to(base))
            for pattern in disallowed_patterns:
                if fnmatch(rel_path, pattern):
                    raise PathValidationError(
                        f"Path matches disallowed pattern {pattern}: {path}",
                        "PATTERN_DISALLOWED",
                        str(path)
                    )

        return resolved

    @staticmethod
    def validate_batch(
        paths: List[str | Path],
        base_dir: str | Path,
        **kwargs
    ) -> List[Path]:
        """Validate multiple paths in batch."""
        return [PathValidator.validate(p, base_dir, **kwargs) for p in paths]

    @staticmethod
    def check(
        path: str | Path,
        base_dir: str | Path,
        **kwargs
    ) -> dict:
        """Check if path is valid without raising.

        Returns:
            dict with keys: valid (bool), error (str), resolved_path (Path)
        """
        try:
            resolved = PathValidator.validate(path, base_dir, **kwargs)
            return {"valid": True, "resolved_path": resolved}
        except PathValidationError as e:
            return {"valid": False, "error": str(e)}
```

**Tests:** `kb/security/test_path_validator.py`

```python
import pytest
import tempfile
import os
from pathlib import Path
from kb.security.path_validator import PathValidator, PathValidationError


def test_path_traversal_protection():
    base = Path("/home/user/project")

    with pytest.raises(PathValidationError) as exc:
        PathValidator.validate("../etc/passwd", base)
    assert "PATH_TRAVERSAL" in str(exc.value.code)


def test_absolute_path_outside_base():
    base = Path("/home/user/project")

    with pytest.raises(PathValidationError) as exc:
        PathValidator.validate("/etc/passwd", base)
    assert "PATH_TRAVERSAL" in str(exc.value.code)


def test_valid_relative_path():
    base = Path("/home/user/project")
    result = PathValidator.validate("src/index.py", base)
    assert result == base / "src/index.py"


def test_symlink_rejection():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        link_path = base / "link"
        target = base / "target.txt"
        target.touch()
        link_path.symlink_to(target)

        with pytest.raises(PathValidationError) as exc:
            PathValidator.validate("link", base, allow_symlinks=False)
        assert "SYMLINK_DISALLOWED" in str(exc.value.code)


def test_extension_filtering():
    base = Path("/home/user/project")

    with pytest.raises(PathValidationError) as exc:
        PathValidator.validate(
            "script.sh",
            base,
            allowed_extensions=[".py", ".toml"]
        )
    assert "INVALID_EXTENSION" in str(exc.value.code)


def test_batch_validation():
    base = Path("/home/user/project")
    paths = ["src/a.py", "src/b.py", "lib/c.py"]
    results = PathValidator.validate_batch(paths, base)
    assert len(results) == 3
    assert all(isinstance(p, Path) for p in results)


def test_check_method_safe():
    base = Path("/home/user/project")
    result = PathValidator.check("src/index.py", base)
    assert result["valid"] is True
    assert "resolved_path" in result


def test_check_method_unsafe():
    base = Path("/home/user/project")
    result = PathValidator.check("../etc/passwd", base)
    assert result["valid"] is False
    assert "error" in result
```

#### 1.1.3 Apply Validation to All File Operations

**High Priority Updates:**

1. **agent-core/src/storage/toml-writer.ts**

```typescript
// BEFORE:
constructor(private filepath: string) {}

// AFTER:
import { PathValidator } from '../../../shared/security/path-validator';

constructor(
  private filepath: string,
  private baseDir: string = process.cwd()
) {
  // Validate on construction
  this.filepath = PathValidator.validate(filepath, {
    baseDir: this.baseDir,
    allowSymlinks: false,
    allowedExtensions: ['.toml'],
    disallowedPatterns: ['**/node_modules/**', '**/.git/**']
  });
}
```

2. **kb/api/app.py:654**

```python
# BEFORE:
text = file_path.read_text(encoding="utf-8", errors="ignore")

# AFTER:
from kb.security.path_validator import PathValidator, PathValidationError

try:
    validated_path = PathValidator.validate(
        file_path,
        base_dir=repo_root,
        allow_symlinks=False,
        must_exist=True,
        allowed_extensions=['.py', '.js', '.ts', '.tsx', '.jsx', '.md', '.txt']
    )
    text = validated_path.read_text(encoding="utf-8", errors="ignore")
except PathValidationError as e:
    logger.warning(f"Skipping file due to security check: {e}")
    continue
```

3. **All other file operations** - Apply similar pattern

**Acceptance Criteria:**
- [ ] PathValidator implemented for TypeScript with 100% test coverage
- [ ] PathValidator implemented for Python with 100% test coverage
- [ ] All 20+ identified file operation locations updated
- [ ] Security penetration testing passed (attempt path traversal, symlink attacks)
- [ ] CI pipeline includes security checks
- [ ] Documentation: security guidelines for file operations

**Estimated Effort:** 3 days
- Day 1: Implement PathValidator modules + comprehensive tests
- Day 2: Apply to all TypeScript/JS file operations
- Day 3: Apply to all Python file operations + penetration testing

---

## WP2: Architecture Refactoring

### Issue 2.1: Agent Core V1 Deprecation

**Decision:** No users, no backward compatibility needed. Complete removal of V1.

**Problem:** Dual agent-core and agent-core-v2 creates maintenance burden with zero benefit (no existing users).

**Specification:**

#### 2.1.1 Capability Verification

**Ensure V2 has ALL V1 capabilities:**

| V1 Capability | V2 Status | Notes |
|---------------|-----------|-------|
| Basic task execution | ✅ Present | EditorWorkflow |
| KB search integration | ✅ Present | ContextBuilder |
| Claude CLI auth | ✅ Present | ClaudeProvider |
| Streaming responses | ✅ Present | AsyncIterator pattern |
| State persistence | ✅ Present | StateStore (TOML) |
| Conversation history | ✅ Present | Built into StateStore |
| Tool execution | ✅ Present | ClaudeProvider.execute |
| Architect mode | ✅ Present | ArchitectWorkflow (V2 only) |
| Multi-model | ✅ Present | Model selection per phase (V2 only) |

**Verdict:** V2 is feature-complete superset of V1. Safe to delete V1.

#### 2.1.2 Deprecation Plan

**Timeline:** Immediate (no gradual migration needed)

**Steps:**
1. **Audit dependencies** - Ensure nothing in vscode-extension imports from agent-core
2. **Update vscode-extension** - Point to agent-core-v2
3. **Delete agent-core/** entirely
4. **Update docs** - Remove all V1 references
5. **Rename agent-core-v2** → **agent-core** (optional, can keep v2 name)

#### 2.1.3 Implementation

**File:** `vscode-extension/src/agent/bridge.ts`

```typescript
// BEFORE:
import { AgentCore } from '../../../agent-core/src/main';

// AFTER:
import { Orchestrator } from '../../../agent-core-v2/src/orchestrator/orchestrator';
import { EditorWorkflow } from '../../../agent-core-v2/src/workflows/editor-workflow';

export class AgentBridge {
  private orchestrator: Orchestrator;

  constructor(workspaceRoot: string) {
    this.orchestrator = new Orchestrator({
      workspaceRoot,
      defaultWorkflow: 'editor', // Use fast editor workflow by default
      stateStore: new StateStore({ storagePath: '.dolphin' })
    });
  }

  async sendMessage(message: string, context: any) {
    // Use V2 orchestrator
    for await (const update of this.orchestrator.executeTask({
      mode: 'editor',
      message,
      context
    })) {
      this.handleUpdate(update);
    }
  }
}
```

**Deletion:**
```bash
# Delete entire agent-core V1 directory
rm -rf agent-core/

# Update package.json references
# Update tsconfig.json paths
# Update documentation
```

**Acceptance Criteria:**
- [ ] agent-core/ directory deleted
- [ ] vscode-extension uses agent-core-v2 exclusively
- [ ] All tests pass after deletion
- [ ] No references to V1 in codebase
- [ ] Documentation updated
- [ ] Build and deployment scripts updated

**Estimated Effort:** 1 day
- Audit dependencies: 2 hours
- Update vscode-extension: 3 hours
- Delete & cleanup: 1 hour
- Testing: 2 hours

---

### Issue 2.2: Extract Phase Strategies from ArchitectWorkflow

(Same as original specification - this is still needed)

**Problem:** 695-line ArchitectWorkflow class with embedded phase logic.

**Solution:** Extract ResearchPhase, ClarificationPhase, PlanningPhase into separate strategy classes.

[Keep original specification for Issue 2.2 - no changes needed]

**Acceptance Criteria:**
- [ ] Phase interface defined
- [ ] ResearchPhase extracted (~120 lines)
- [ ] ClarificationPhase extracted (~130 lines)
- [ ] PlanningPhase extracted (~140 lines)
- [ ] ArchitectWorkflow reduced to <150 lines
- [ ] All tests pass
- [ ] Phase reuse demonstrated

**Estimated Effort:** 3 days

---

## WP3: Code Quality Improvements

[Keep original specifications for WP3.1 and WP3.2 - no changes]

**Estimated Effort:** 5 days total

---

## WP4: Precision Enhancements

[Keep original specifications for WP4.1 and WP4.2 - no changes]

**Estimated Effort:** 7 days total (including A/B testing)

---

## WP5: Performance Optimization

[Keep original specifications for WP5.1 and WP5.2 - no changes]

**Estimated Effort:** 3 days total

---

## WP6: Style, Consistency & CI/CD

### Issue 6.1: Standardized Error Messages

[Keep original specification - no changes]

**Estimated Effort:** 2 days

---

### Issue 6.2: Import Organization

[Keep original specification - no changes]

**Estimated Effort:** 1 day

---

### Issue 6.3: CI/CD Pipeline for Code Quality

**NEW SECTION**

**Problem:** No automated enforcement of code quality standards, security checks, or style guidelines.

**Specification:**

#### 6.3.1 GitHub Actions Workflow

**File:** `.github/workflows/code-quality.yml`

```yaml
name: Code Quality

on:
  push:
    branches: [main, develop, develop-architect]
  pull_request:
    branches: [main, develop]

jobs:
  security-scan:
    name: Security Scanning
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run path traversal tests
        run: |
          npm run test:security
          pytest tests/security/

      - name: Audit dependencies
        run: |
          npm audit --audit-level=high
          pip-audit

      - name: Scan for secrets
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD

  typescript-quality:
    name: TypeScript Quality Checks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: oven-sh/setup-bun@v1
        with:
          bun-version: latest

      - name: Install dependencies
        run: bun install

      - name: Type checking
        run: bun run typecheck

      - name: Linting
        run: bun run lint

      - name: Format check
        run: bun run format:check

      - name: Import order check
        run: bun run lint:imports

      - name: Run tests with coverage
        run: bun run test:coverage

      - name: Check coverage thresholds
        run: |
          bun run coverage:check --branches=90 --functions=90 --lines=90

  python-quality:
    name: Python Quality Checks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"

      - name: Type checking
        run: mypy kb/ --strict

      - name: Linting
        run: ruff check kb/

      - name: Format check
        run: black --check kb/

      - name: Import sorting
        run: isort --check-only kb/

      - name: Run tests with coverage
        run: pytest --cov=kb --cov-report=xml --cov-fail-under=90

  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4

      - uses: oven-sh/setup-bun@v1

      - name: Start KB server
        run: |
          cd kb
          uv pip install -e .
          dolphin serve --port 7777 &
          sleep 5

      - name: Run integration tests
        run: bun test:integration

      - name: E2E smoke tests
        run: bun test:e2e

  performance-benchmarks:
    name: Performance Regression Check
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: oven-sh/setup-bun@v1

      - name: Checkout base branch
        run: git checkout ${{ github.base_ref }}

      - name: Run baseline benchmarks
        run: bun run benchmark --json > baseline.json

      - name: Checkout PR branch
        run: git checkout ${{ github.head_ref }}

      - name: Run PR benchmarks
        run: bun run benchmark --json > pr.json

      - name: Compare results
        run: |
          bun run benchmark:compare baseline.json pr.json
          # Fail if >10% regression
          bun run benchmark:check --max-regression=0.10

  docker-build:
    name: Docker Build Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t dolphin:test .

      - name: Test Docker image
        run: |
          docker run --rm dolphin:test dolphin --version
          docker run --rm dolphin:test pytest --version
```

#### 6.3.2 Pre-commit Hooks

**File:** `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: local
    hooks:
      - id: security-path-check
        name: Security path validation check
        entry: bun run test:security
        language: system
        pass_filenames: false

      - id: typescript-typecheck
        name: TypeScript type check
        entry: bun run typecheck
        language: system
        types: [typescript]
        pass_filenames: false

      - id: eslint
        name: ESLint
        entry: bun run lint --fix
        language: system
        types: [typescript]

      - id: python-black
        name: Black formatter
        entry: black
        language: system
        types: [python]

      - id: python-ruff
        name: Ruff linter
        entry: ruff check --fix
        language: system
        types: [python]

      - id: python-mypy
        name: MyPy type check
        entry: mypy
        language: system
        types: [python]
```

#### 6.3.3 Package Scripts

**File:** `package.json`

```json
{
  "scripts": {
    "typecheck": "tsc --noEmit",
    "lint": "eslint . --ext .ts,.tsx",
    "lint:fix": "eslint . --ext .ts,.tsx --fix",
    "lint:imports": "eslint . --ext .ts,.tsx --rule 'import/order: error'",
    "format": "prettier --write \"**/*.{ts,tsx,json,md}\"",
    "format:check": "prettier --check \"**/*.{ts,tsx,json,md}\"",
    "test": "bun test",
    "test:coverage": "bun test --coverage",
    "test:security": "bun test shared/security/__tests__/",
    "test:integration": "bun test --filter integration",
    "test:e2e": "bun test --filter e2e",
    "coverage:check": "bun run test:coverage && node scripts/check-coverage.js",
    "benchmark": "bun run shared/ipc/benchmark.ts",
    "benchmark:compare": "node scripts/compare-benchmarks.js"
  }
}
```

#### 6.3.4 Coverage Requirements

**File:** `scripts/check-coverage.js`

```javascript
#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const coverageFile = path.join(__dirname, '../coverage/coverage-summary.json');
const coverage = JSON.parse(fs.readFileSync(coverageFile, 'utf8'));

const thresholds = {
  branches: 90,
  functions: 90,
  lines: 90,
  statements: 90
};

const total = coverage.total;
let failed = false;

for (const [metric, threshold] of Object.entries(thresholds)) {
  const pct = total[metric].pct;
  const pass = pct >= threshold;

  console.log(`${metric}: ${pct.toFixed(2)}% (threshold: ${threshold}%)`);

  if (!pass) {
    console.error(`❌ ${metric} coverage below threshold`);
    failed = true;
  }
}

if (failed) {
  process.exit(1);
}

console.log('✅ All coverage thresholds met');
```

**Acceptance Criteria:**
- [ ] GitHub Actions workflow created and passing
- [ ] Pre-commit hooks installed and working
- [ ] Security scans pass (no vulnerabilities)
- [ ] Type checking enforced (TypeScript + Python)
- [ ] Linting enforced with auto-fix
- [ ] Code coverage >90% on all metrics
- [ ] Performance benchmarks track regressions
- [ ] Integration tests run on every PR
- [ ] Docker build tested in CI

**Estimated Effort:** 2 days
- Day 1: Create workflows, configure tools
- Day 2: Test, debug, document

---

## Implementation Timeline

### Simplified Timeline (16 days total)

**Week 1 (Days 1-5): Critical Fixes**
- Day 1-3: WP1 - Universal path validation
- Day 4-5: WP3.1 - Structured logging (TypeScript)

**Week 2 (Days 6-10): Quality & Precision**
- Day 6-7: WP3.1 - Structured logging (Python) + WP3.2 - Config constants
- Day 8-9: WP4.2 - Token counting
- Day 10: WP5.2 - Single-pass processing

**Week 3 (Days 11-16): Architecture & Infrastructure**
- Day 11-12: WP5.1 - Connection pooling
- Day 13: WP2.1 - Delete V1
- Day 14-15: WP2.2 - Phase extraction
- Day 16: WP6 - Error messages, imports, CI/CD setup

**Additional (Optional):** WP4.1 - BM25 normalization with A/B testing (1 week)

**Total:** 3 weeks core work + 1 week optional precision improvement

---

## Testing Requirements

### Security Testing
- [ ] Path traversal penetration tests (automated + manual)
- [ ] Fuzzing with malicious inputs
- [ ] Dependency audit (npm audit + pip-audit)
- [ ] Secret scanning (trufflehog)

### Performance Testing
- [ ] Load testing (simulate 1000 concurrent queries)
- [ ] Stress testing (10K+ queries/sec)
- [ ] Memory profiling (no leaks)
- [ ] Latency benchmarks (p50, p95, p99)

### Functional Testing
- [ ] All existing tests pass
- [ ] New functionality >95% coverage
- [ ] Integration tests for all refactored components
- [ ] E2E smoke tests

---

## Success Metrics

### Performance
- [ ] Search latency p95 < 500ms
- [ ] Concurrent query throughput >2000/sec
- [ ] Memory usage <2GB per instance

### Quality
- [ ] Zero critical security vulnerabilities
- [ ] Test coverage >90%
- [ ] Code duplication <5%
- [ ] All CI checks passing

### Developer Experience
- [ ] Clear error messages with context
- [ ] Comprehensive security guidelines
- [ ] Automated quality enforcement
- [ ] Fast feedback loop (<5 min CI)

---

## Dependencies

### External Dependencies
- `minimatch` - for path pattern matching
- `trufflesecurity/trufflehog` - secret scanning
- `pip-audit` - Python dependency scanning

### Internal Dependencies
- None - no backward compatibility needed

---

### Code Review Checklist

Before merging any changes:
- [ ] All tests pass (unit + integration + security)
- [ ] Code coverage maintained (>90%)
- [ ] Documentation updated
- [ ] Security review completed (especially file operations)
- [ ] Performance benchmarks run (no regressions)
- [ ] CI pipeline passes

---

**Document Changelog:**

| Version | Date | Changes |
|---------|------|---------|
| 1.1 | 2025-11-12 | Updated WP1 with comprehensive audit, simplified WP2 (no V1 compat), added CI/CD to WP6 |
| 1.0 | 2025-11-12 | Initial specification |

---

**End of Specification Document**
