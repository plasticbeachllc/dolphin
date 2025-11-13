# Security Guidelines for Dolphin Development

**Version:** 1.0
**Date:** 2025-11-13
**Status:** Active

## Executive Summary

This document provides security guidelines for developing and maintaining the Dolphin codebase. All developers must follow these guidelines to prevent security vulnerabilities, particularly path traversal attacks.

---

## Table of Contents

1. [Path Traversal Protection](#path-traversal-protection)
2. [File Operation Security](#file-operation-security)
3. [Input Validation](#input-validation)
4. [Security Testing](#security-testing)
5. [Code Review Checklist](#code-review-checklist)

---

## Path Traversal Protection

### Overview

Path traversal (also known as directory traversal) is a web security vulnerability that allows attackers to access files and directories outside the intended scope. Attackers can use special character sequences like `../` to navigate up the directory tree.

### Attack Vectors

Common path traversal attack techniques include:

1. **Basic traversal**: `../etc/passwd`, `../../etc/passwd`
2. **URL encoding**: `%2e%2e/etc/passwd`, `..%2fetc/passwd`
3. **Double URL encoding**: `%252e%252e/etc/passwd`
4. **Null byte injection**: `file.txt\0.jpg`
5. **Unicode homoglyphs**: `\u2024\u2024/etc/passwd` (Unicode dot leader)
6. **Windows paths**: `..\..\windows\system32`
7. **UNC paths**: `\\server\share\file`
8. **Mixed techniques**: Combining multiple attack vectors

### Solution: PathValidator

Dolphin provides secure `PathValidator` classes for both TypeScript and Python that prevent all known path traversal attacks.

#### TypeScript Usage

```typescript
import { PathValidator } from "../../../shared/security/path-validator";

// Basic usage
const validator = new PathValidator({ baseDir: workspaceRoot });
const safePath = validator.validate(userInputPath);

// With options
const validator = new PathValidator({
  baseDir: workspaceRoot,
  allowSymlinks: false, // Reject symlinks (default)
  mustExist: false, // Don't require file to exist (default)
  allowedExtensions: [".ts", ".js"], // Only allow specific extensions
  disallowedPatterns: ["^\."], // Reject hidden files
  errorPrefix: "Security violation", // Custom error messages
});

const safePath = validator.validate("src/file.ts");
```

#### Python Usage

```python
from kb.security import PathValidator, PathValidationError

# Basic usage
validator = PathValidator(base_dir=repo_root)
try:
    safe_path = validator.validate(user_input_path)
except PathValidationError as e:
    print(f"Attack blocked: {e.reason}")

# With options
validator = PathValidator(
    base_dir=repo_root,
    allow_symlinks=False,           # Reject symlinks (default)
    must_exist=False,                # Don't require file to exist (default)
    allowed_extensions=['.py', '.txt'], # Only allow specific extensions
    disallowed_patterns=[r'^\\.'],  # Reject hidden files
    error_prefix='Security violation' # Custom error messages
)

safe_path = validator.validate('src/module.py')
```

### When to Use PathValidator

**ALWAYS use PathValidator when:**

- Reading file paths from user input
- Accepting file paths from API requests
- Processing file paths from external sources (MCP tools, etc.)
- Constructing file paths from IDs or names
- Any operation that could access files outside the workspace

**Examples that REQUIRE validation:**

- ✅ `TOMLWriter(userFilePath, workspace)` - validates path
- ✅ `fs.readFile(validator.validate(inputPath))`
- ✅ `file_path.read_text()` where file_path from user

**Safe operations that DON'T need validation:**

- ✅ Reading bundled templates: `Path(__file__).parent / 'template.toml'`
- ✅ Hardcoded paths: `Path.home() / '.dolphin' / 'config.toml'`
- ✅ System paths: `os.tmpdir()`

---

## File Operation Security

### TypeScript File Operations

```typescript
// ❌ UNSAFE - No validation
async function readUserFile(filepath: string, workspace: string) {
  const fullPath = path.join(workspace, filepath);
  return await fs.readFile(fullPath, "utf-8");
}

// ✅ SAFE - With validation
async function readUserFile(filepath: string, workspace: string) {
  const validator = new PathValidator({ baseDir: workspace });
  const safePath = validator.validate(filepath);
  return await fs.readFile(safePath, "utf-8");
}
```

### Python File Operations

```python
# ❌ UNSAFE - No validation
def read_user_file(filepath: str, repo_root: Path) -> str:
    full_path = repo_root / filepath
    return full_path.read_text()

# ✅ SAFE - With validation
def read_user_file(filepath: str, repo_root: Path) -> str:
    validator = PathValidator(base_dir=repo_root)
    safe_path = validator.validate(filepath)
    return safe_path.read_text()
```

### High-Risk File Operations

The following operations are particularly vulnerable if not properly validated:

| Operation       | TypeScript                             | Python                           | Risk Level |
| --------------- | -------------------------------------- | -------------------------------- | ---------- |
| Read file       | `fs.readFile()`, `fs.readFileSync()`   | `Path.read_text()`, `open()`     | HIGH       |
| Write file      | `fs.writeFile()`, `fs.writeFileSync()` | `Path.write_text()`, `open()`    | CRITICAL   |
| Delete file     | `fs.unlink()`, `fs.unlinkSync()`       | `Path.unlink()`, `os.remove()`   | CRITICAL   |
| Check existence | `fs.existsSync()`, `fs.access()`       | `Path.exists()`                  | MEDIUM     |
| List directory  | `fs.readdir()`, `fs.readdirSync()`     | `Path.iterdir()`, `os.listdir()` | MEDIUM     |

---

## Input Validation

### General Principles

1. **Validate all external input** - Treat all user input, API parameters, and external data as untrusted
2. **Whitelist over blacklist** - Define what IS allowed rather than what ISN'T
3. **Fail securely** - When validation fails, deny access and log the attempt
4. **Defense in depth** - Use multiple layers of validation

### Path Validation Checklist

When accepting file paths:

- [ ] Use PathValidator for all user-provided paths
- [ ] Set appropriate `baseDir` to limit access scope
- [ ] Consider if `allowSymlinks` should be false (recommended)
- [ ] Use `allowedExtensions` if only specific file types are needed
- [ ] Use `disallowedPatterns` to reject hidden files, backups, etc.
- [ ] Handle `PathValidationError` exceptions appropriately
- [ ] Log validation failures for security monitoring

### File System Operation Checklist

When performing file operations:

- [ ] Validate path before any file system access
- [ ] Use absolute paths internally after validation
- [ ] Never construct paths using string concatenation with user input
- [ ] Check file permissions before access
- [ ] Handle errors gracefully without exposing path information
- [ ] Log file operations for audit trails

---

## Security Testing

### Automated Security Tests

Dolphin includes a comprehensive penetration testing script that validates path traversal protection:

```bash
# Run security penetration tests
python scripts/security-pentest.py

# Expected output:
# ✓ ALL SECURITY TESTS PASSED!
# Passed: 27
# Failed: 0
```

### Test Categories

The penetration tests cover:

1. **Basic Path Traversal** (5 tests)
   - Simple, double, triple parent traversal
   - Traversal in middle of path
   - Complex nested traversal

2. **URL Encoding Attacks** (4 tests)
   - Single URL encoding
   - Double URL encoding
   - Mixed encoding techniques
   - URL-encoded slashes

3. **Null Byte Attacks** (2 tests)
   - Null bytes at end of path
   - Null bytes in middle of path

4. **Absolute Path Attacks** (3 tests)
   - Unix absolute paths outside workspace
   - Absolute paths within workspace (allowed)
   - Absolute paths to system directories

5. **Unicode and Special Characters** (3 tests)
   - Unicode homoglyph attacks
   - Windows path separators
   - UNC network paths

6. **Edge Cases and Advanced Techniques** (10 tests)
   - Empty strings
   - Current directory references
   - Valid relative paths
   - Paths with spaces
   - Multiple slashes
   - Complex valid path navigation

### Manual Security Review

During code reviews, check for:

1. **Unvalidated file paths** - Search for `readFile`, `writeFile`, `Path()`, `open()`
2. **String concatenation** - Look for `path + userInput` patterns
3. **Missing error handling** - Ensure validation errors are caught
4. **Overly permissive validators** - Check `allowSymlinks`, `allowedExtensions`

### Security Regression Testing

To prevent security regressions:

1. Run penetration tests in CI/CD pipeline
2. Add new tests when new attack vectors are discovered
3. Review all changes to PathValidator carefully
4. Maintain test coverage above 90% for security modules

---

## Code Review Checklist

### For Reviewers

When reviewing code that handles file paths:

- [ ] All user-provided paths use PathValidator
- [ ] Appropriate `baseDir` is set for the context
- [ ] Security options (symlinks, extensions) are appropriate
- [ ] Error handling doesn't expose sensitive path information
- [ ] No string concatenation used for path construction
- [ ] File operations have proper permission checks
- [ ] Security tests cover new functionality
- [ ] No hardcoded credentials or secrets in file paths

### For Developers

Before submitting code:

- [ ] Run security penetration tests locally
- [ ] Add tests for new file operations
- [ ] Document any security assumptions
- [ ] Use PathValidator for ALL user input paths
- [ ] Handle PathValidationError gracefully
- [ ] Log security-relevant operations
- [ ] Test with malicious input examples

---

## Examples and Patterns

### Pattern: File Upload Handler

```typescript
// ✅ SAFE file upload handler
async function handleFileUpload(
  uploadPath: string,
  content: Buffer,
  workspaceRoot: string
): Promise<void> {
  // Validate path
  const validator = new PathValidator({
    baseDir: workspaceRoot,
    allowedExtensions: [".txt", ".json", ".md"],
    disallowedPatterns: ["^\\.", ".*\\.tmp$"], // No hidden or temp files
  });

  try {
    const safePath = validator.validate(uploadPath);

    // Additional security: check file size
    if (content.length > 10 * 1024 * 1024) {
      // 10MB limit
      throw new Error("File too large");
    }

    // Write file
    await fs.writeFile(safePath, content);
    console.log(`File uploaded: ${uploadPath}`);
  } catch (error) {
    if (error instanceof PathValidationError) {
      console.error(`Security: blocked upload attempt - ${error.reason}`);
      throw new Error("Invalid file path");
    }
    throw error;
  }
}
```

### Pattern: Repository File Access

```python
# ✅ SAFE repository file reader
def read_repo_file(repo_id: int, file_path: str) -> str:
    """Read a file from a repository with security validation."""
    # Get repository root
    repo = get_repository(repo_id)
    repo_root = Path(repo['root_path'])

    # Validate path
    validator = PathValidator(
        base_dir=repo_root,
        must_exist=True,  # File must exist
        allow_symlinks=False,  # No symlinks
        allowed_extensions=['.py', '.ts', '.js', '.md', '.txt']
    )

    try:
        safe_path = validator.validate(file_path)
        return safe_path.read_text(encoding='utf-8')
    except PathValidationError as e:
        logger.warning(f"Security: blocked file access attempt - {e.reason}")
        raise HTTPException(
            status_code=403,
            detail="Access denied: invalid file path"
        )
```

---

## Incident Response

### If You Discover a Security Vulnerability

1. **Do NOT commit the fix immediately** - This reveals the vulnerability
2. **Report to security lead** - Contact the team lead privately
3. **Document the issue** - Include attack vector, impact, and reproduction steps
4. **Develop fix privately** - Create fix in a private branch
5. **Test thoroughly** - Ensure fix doesn't break functionality
6. **Deploy urgently** - Security fixes take priority
7. **Update tests** - Add test case to prevent regression

### If You Detect an Attack Attempt

1. **Log the details** - Capture attack vector, timestamp, source
2. **Block the request** - Return generic error message
3. **Alert security team** - Report the attempt
4. **Monitor for patterns** - Check for coordinated attacks
5. **Review logs** - Look for successful exploits
6. **Update defenses** - Add new test cases if needed

---

## References

- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [CWE-22: Improper Limitation of a Pathname](https://cwe.mitre.org/data/definitions/22.html)
- Dolphin PathValidator Implementation: `shared/security/path-validator.ts`, `kb/security/path_validator.py`
- Dolphin Security Tests: `scripts/security-pentest.py`

---

## Updates and Maintenance

This document should be updated when:

- New attack vectors are discovered
- PathValidator implementation changes
- New security patterns are established
- Security incidents occur

**Document Owner**: Development Team
**Review Schedule**: Quarterly or after security incidents
**Last Updated**: 2025-11-13
