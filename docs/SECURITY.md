# Security Guidelines

## Threat Model

Dolphin currently runs **local-only** — the API server, MCP bridge, and storage all live on the developer's machine. There is no network-facing attack surface today.

The primary risk is **path traversal**: MCP clients and CLI users submit file paths that could escape the workspace root. All other input validation follows from this.

> **Future work:** When Dolphin supports remote hosting with multiple clients, this document will expand to cover authentication, transport security, and multi-tenant isolation.

---

## Path Traversal Protection

### PathValidator

All user-controlled file paths **must** go through `PathValidator` before any filesystem operation.

**TypeScript** (`shared/security/path-validator.ts`):

```typescript
import { PathValidator } from "../../../shared/security/path-validator";

const validator = new PathValidator({
  baseDir: workspaceRoot,
  allowSymlinks: false,
  allowedExtensions: [".ts", ".js"],
});
const safePath = validator.validate(userInputPath);
```

**Python** (`kb/security/path_validator.py`):

```python
from kb.security import PathValidator, PathValidationError

validator = PathValidator(base_dir=repo_root, allow_symlinks=False)
try:
    safe_path = validator.validate(user_input_path)
except PathValidationError as e:
    logger.warning(f"Blocked path traversal: {e.reason}")
```

### When validation is required

- File paths from API requests, MCP tools, or CLI arguments
- Paths constructed from user-supplied IDs or names
- Any path that could reference files outside the workspace

Hardcoded paths and bundled templates do **not** need validation.

---

## Developer Checklist

Before submitting code that touches file paths:

- [ ] All user-provided paths use `PathValidator`
- [ ] `baseDir` is scoped to the correct workspace root
- [ ] `PathValidationError` is caught and logged (without leaking full paths)
- [ ] No path construction via string concatenation with user input
- [ ] Run `python scripts/security-pentest.py` locally (27 tests covering basic traversal, URL encoding, null bytes, unicode homoglyphs, absolute/UNC paths, and edge cases)

---

## CI/CD

The **Security Scan** GitHub Action runs on every PR:

- **Python:** `pip-audit` checks for known CVEs
- **TypeScript:** `bun audit` covers root workspace and `mcp-bridge/`

PRs are blocked until vulnerabilities are resolved.

---

## References

- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [CWE-22: Improper Limitation of a Pathname](https://cwe.mitre.org/data/definitions/22.html)
- Penetration tests: `scripts/security-pentest.py`
