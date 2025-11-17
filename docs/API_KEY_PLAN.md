# Dolphin KB API Key Unification Plan (Option 2)

**Status:** Draft implementation plan  
**Scope:** Shared KB API key for all Dolphin interfaces (CLI, REST API, VS Code extension, Agent Core, MCP bridge) with zero per‑user manual configuration.

---

## 1. Problem Statement and Goals

Today:

- The KB REST API enforces an API key on all `/v1/**` endpoints via the `X-API-Key` header compared against `DOLPHIN_API_KEY`.
- Users are expected to export `DOLPHIN_API_KEY` manually (or configure it via VS Code), and different Dolphin entry points may not be consistently configured.

We want **Option 2**:

- A **single, per-user KB API key** persisted under the user’s home directory.
- On first use, Dolphin **automatically creates** this key.
- All Dolphin components that talk to the KB:
  - Discover the same key with a consistent precedence:
    - By default, read from `~/.dolphin/kb_api_key`, **creating it automatically** on first use via officially supported entry points.
    - Environment variables (`DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY`) remain available as an advanced override for tests/CI and future remote deployments, but are **not required for normal usage**.
  - Always send `X-API-Key` for KB requests.
- No manual `.env` editing for a typical desktop/CLI user.

Security requirements:

- KB API key must be **high-entropy** and not guessable.
- Stored in a file with **user-only permissions** on POSIX.
- Works cross-platform (macOS, Linux, Windows), relying on user home directory.
- Existing tests that explicitly set `DOLPHIN_API_KEY` must continue to behave exactly as before.

Non-goals:

- Multi-tenant / multi-user server security policies (handled separately via gateway/service deployments).

---

## 2. High-Level Design

### 2.1 Single Per-User KB API Key

- Canonical location: `~/.dolphin/kb_api_key` (text file, single line).
- Contents: opaque high-entropy string (64 hex chars from 32 random bytes).
- Access pattern:
  1. Official entry points resolve or create `~/.dolphin/kb_api_key` on first use.
  2. Other components (Agent Core, MCP bridge, etc.) **only read** the key via shared helpers; they never create it themselves.
  3. Env overrides (`DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY`) are respected when explicitly set (primarily in tests or remote/server deployments).

### 2.2 Components That Must Participate

Python / KB:

- `kb/api/app.py`: already enforces `DOLPHIN_API_KEY` via middleware.
- `kb/cli.py`: `dolphin init`, `dolphin serve`.

TypeScript / Node:

- VS Code extension: `vscode-extension/src/extension.ts`, KB consumers (file watcher, auto-sync, drift-detector, webview).
- Agent Core: `agent-core/src/main.ts`, `agent-core/src/context/context-builder.ts`, `agent-core/src/kb/index-queue.ts`.
- MCP bridge: `mcp-bridge/src/rest/client.ts` (REST client), `mcp-bridge/src/cli.ts` (env bootstrap).

Shared utilities:

- Python helper for key discovery/creation.
- Node helper for key discovery and (where allowed) creation.

### 2.3 Official Key Creators vs Read-Only Consumers

**Official key creators (allowed to create/rotate `~/.dolphin/kb_api_key` automatically):**

- Python CLI:
  - `dolphin init`
  - `dolphin serve`
- VS Code extension:
  - Activation flow via `initializeKbApiKey`, using the shared Node helper.
- MCP CLI:
  - `dolphin-mcp` (when invoked as a standalone MCP server).

These are the **only** entry points that should call “create” semantics in the helpers.

**Read-only consumers (must never create keys themselves):**

- Agent Core (when started via VS Code).
- MCP Bridge REST client (`mcp-bridge/src/rest/client.ts`) when used as a library.
- Any future programmatic SDKs or tools.

Read-only consumers:

- Resolve the key via env first (for advanced/remote scenarios).
- Then fall back to reading from `~/.dolphin/kb_api_key`, **without creating it** if missing.

### 2.4 Precedence and Backwards Compatibility

Precedence rules (for all components):

1. **Environment override**
   - If `DOLPHIN_API_KEY` or `DOLPHIN_KB_API_KEY` is set in `process.env` / `os.environ`, use that as the effective key and **do not create or modify** the key file.
   - This path is primarily for tests/CI and for future remote KB server deployments where a secrets manager injects the key.
2. **Per-user key file**
   - If no env var is set, look for `~/.dolphin/kb_api_key`.
   - If present, read and use its contents.
3. **First-use creation**
   - If file is missing, generate a new key, write to `~/.dolphin/kb_api_key`, and then use that key.
   - Creation is only performed by official entry points listed in §2.3.

This allows:

- Python CLI `dolphin serve` and VS Code extension to interoperate without the user doing anything.
- Dev/test harnesses and CI to retain full control via env when desired, without impacting everyday developer flows.

---

## 3. Python Side Design

### 3.1 New Helper: `kb/api_key.py`

**File:** `kb/api_key.py` (new)

Responsibilities:

- Encapsulate the logic to resolve or create the KB API key.
- Provide a synchronized, single-process API for:
  - “Read-only” usage (avoid accidental creation).
  - “Get or create” usage (server startup).

#### 3.1.1 Public API (Python)

```python
# kb/api_key.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

KB_API_KEY_FILENAME = "kb_api_key"

def get_kb_key_path() -> Path:
    """Return the canonical path to the KB API key file (~/.dolphin/kb_api_key)."""
    return Path.home() / ".dolphin" / KB_API_KEY_FILENAME

def load_kb_api_key() -> Optional[str]:
    """Load KB API key in read-only mode.

    Precedence:
      1) DOLPHIN_API_KEY env var
      2) DOLPHIN_KB_API_KEY env var
      3) ~/.dolphin/kb_api_key (if present)
    """
    ...

def get_or_create_kb_api_key() -> str:
    """Resolve or create the per-user KB API key.

    If env provides DOLPHIN_API_KEY / DOLPHIN_KB_API_KEY, returns that and
    does NOT touch the key file.

    Otherwise, uses ~/.dolphin/kb_api_key, creating it with a new random
    high-entropy key if it does not exist.
    """
    ...
```

#### 3.1.2 Implementation Sketch (Python)

Key behaviors:

- Use `secrets.token_hex(32)` or similar for random key generation.
- Ensure directory `~/.dolphin` exists with `mode=0o700` on POSIX (best-effort).
- For file creation, use exclusive creation semantics to avoid race conditions:
  - `path.open("x", encoding="utf-8")` or `os.open` with `O_CREAT | O_EXCL`.
  - On `FileExistsError`, re-open in read mode and return contents.
- Ensure file permissions are set to user-only (`0o600`) where OS permits.

Pseudocode:

```python
import os
import secrets
from pathlib import Path
from typing import Optional

KB_API_KEY_FILENAME = "kb_api_key"

def get_kb_key_path() -> Path:
    return Path.home() / ".dolphin" / KB_API_KEY_FILENAME

def _env_override() -> Optional[str]:
    for name in ("DOLPHIN_API_KEY", "DOLPHIN_KB_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    return None

def load_kb_api_key() -> Optional[str]:
    # 1) Env override
    env_val = _env_override()
    if env_val:
        return env_val

    # 2) Existing file (read-only)
    path = get_kb_key_path()
    if not path.exists():
        return None

    data = path.read_text(encoding="utf-8").strip()
    return data or None

def get_or_create_kb_api_key() -> str:
    # 1) Env override wins and avoids touching filesystem
    env_val = _env_override()
    if env_val:
        return env_val

    path = get_kb_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 2) Try reading existing file
    if path.exists():
        data = path.read_text(encoding="utf-8").strip()
        if data:
            return data

    # 3) Create new key with exclusive semantics
    key = secrets.token_hex(32)  # 64 hex chars (~256 bits)

    try:
        # "x" = exclusive creation; fails if file exists
        with path.open("x", encoding="utf-8") as f:
            f.write(key + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Best effort; ignore on platforms that don't support chmod
            pass
        return key
    except FileExistsError:
        # Lost the race; read the file written by another process
        data = path.read_text(encoding="utf-8").strip()
        return data or key  # Fallback to in-memory key if file was somehow empty
```

### 3.2 Integrate with `dolphin init`

**File:** `kb/cli.py`

Current:

```python
@app.command()
def init(
    config_path: Path | None = typer.Option(None, "--config", help="Optional config path."),
) -> None:
    """Initialize the knowledge store (config + SQLite + LanceDB collections)."""
    kb_init(config_path)
```

Planned change:

- After `kb_init(config_path)` completes, ensure the KB API key exists.
- Do not override explicit env settings; we rely on `get_or_create_kb_api_key`’s precedence.

Pseudocode:

```python
from kb.api_key import get_or_create_kb_api_key

@app.command()
def init(
    config_path: Path | None = typer.Option(None, "--config", help="Optional config path."),
) -> None:
    """Initialize the knowledge store (config + SQLite + LanceDB collections)."""
    kb_init(config_path)

    # Ensure per-user KB API key exists for future clients
    try:
        key = get_or_create_kb_api_key()
        # Optionally log a one-time note (stdout or logging) without printing the key
        # typer.echo("KB API key initialized in ~/.dolphin/kb_api_key")
    except Exception as exc:  # pragma: no cover (defensive)
        # Failing to create the key should not break init; server/clients will create on demand.
        _log.warning("Failed to initialize KB API key: %s", exc)
```

### 3.3 Integrate with `dolphin serve`

**File:** `kb/cli.py`

Current:

```python
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(7777, "--port", help="Port to bind to"),
) -> None:
    """Start the dolphin API server."""
    import uvicorn

    uvicorn.run("kb.api.server:app_with_lifespan", host=host, port=port, reload=False)
```

Planned change:

- Before starting Uvicorn, resolve the KB API key and set `os.environ["DOLPHIN_API_KEY"]` if not already set.
- This ensures the FastAPI middleware in `kb/api/app.py` always has a non-empty expected key.

Pseudocode:

```python
import os
from kb.api_key import get_or_create_kb_api_key

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(7777, "--port", help="Port to bind to"),
) -> None:
    """Start the dolphin API server."""
    import uvicorn

    # Ensure DOLPHIN_API_KEY is set for the server process
    if not os.environ.get("DOLPHIN_API_KEY") and not os.environ.get("DOLPHIN_KB_API_KEY"):
        key = get_or_create_kb_api_key()
        os.environ["DOLPHIN_API_KEY"] = key

    uvicorn.run("kb.api.server:app_with_lifespan", host=host, port=port, reload=False)
```

### 3.4 Other Python Callers (Optional)

Anywhere else we spawn the KB server (e.g., a future supervisor or CLI wrapper), we should:

- Either rely on `dolphin serve` logic (preferred).
- Or explicitly call `get_or_create_kb_api_key()` and set `DOLPHIN_API_KEY` in `env` passed to the subprocess.

---

## 4. Node / TypeScript Side Design

### 4.1 Shared Node Helper: `shared/kb-auth.ts`

**File:** `shared/kb-auth.ts` (new)

Responsibilities:

- Mirror Python’s behavior for resolving/creating the KB API key for **Node-based** components.
- Expose two primary functions:
  - `resolveKbApiKey(options?)` – read-only view (checks env, then file; no creation if missing unless configured).
  - `getOrCreateKbApiKey(options?)` – full “env or create file” semantics.

Key design points:

- Use `os.homedir()` to find the user’s home directory.
- Use `fs.mkdirSync(..., { recursive: true })` for `~/.dolphin`.
- Use `fs.openSync(path, "wx", 0o600)` for exclusive creation and `fs.writeFileSync`.
- Handle races with `EEXIST` similarly to Python.

TypeScript interface:

```ts
// shared/kb-auth.ts
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { randomBytes } from "crypto";

export interface KbAuthOptions {
  /** Custom home directory override (mainly for tests) */
  homeDir?: string;
  /** If true, do not create the file when missing */
  readOnly?: boolean;
}

export function getKbKeyPath(opts?: KbAuthOptions): string {
  const home = opts?.homeDir ?? os.homedir();
  return path.join(home, ".dolphin", "kb_api_key");
}

export function resolveKbApiKey(opts?: KbAuthOptions): string | undefined {
  // 1) Env override (advanced/CI/remote usage)
  const envKey =
    process.env.DOLPHIN_API_KEY?.trim() || process.env.DOLPHIN_KB_API_KEY?.trim() || "";
  if (envKey) return envKey;

  // 2) Existing file (read-only by default)
  const keyPath = getKbKeyPath(opts);
  if (!fs.existsSync(keyPath)) {
    // In read-only mode, do not create the file
    return undefined;
  } else {
    const data = fs.readFileSync(keyPath, "utf8").trim();
    if (data) return data;
    // If file is empty, treat as missing and fall through
  }

  // No env override, no usable file contents
  return undefined;
}

export function getOrCreateKbApiKey(opts?: KbAuthOptions): string {
  // 1) Respect env override if present
  const envKey =
    process.env.DOLPHIN_API_KEY?.trim() || process.env.DOLPHIN_KB_API_KEY?.trim() || "";
  if (envKey) return envKey;

  // 2) Try existing file
  const keyPath = getKbKeyPath(opts);
  if (fs.existsSync(keyPath)) {
    const data = fs.readFileSync(keyPath, "utf8").trim();
    if (data) return data;
  }

  // 3) Create new file (only call from official entry points)
  return createKbApiKeyFile(keyPath);
}

function createKbApiKeyFile(keyPath: string): string {
  const dir = path.dirname(keyPath);
  fs.mkdirSync(dir, { recursive: true });

  const key = randomBytes(32).toString("hex"); // 64 hex chars

  try {
    const fd = fs.openSync(keyPath, "wx", 0o600);
    try {
      fs.writeFileSync(fd, key + "\n", { encoding: "utf8" });
    } finally {
      fs.closeSync(fd);
    }
    return key;
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code === "EEXIST") {
      // Lost race; read existing value
      const data = fs.readFileSync(keyPath, "utf8").trim();
      return data || key;
    }
    throw err;
  }
}
```

### 4.2 VS Code Extension Integration

**File:** `vscode-extension/src/extension.ts`

Current behavior:

- `initializeKbApiKey(context)`:
  - Checks env (`DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY`).
  - Then SecretStorage (`KB_API_KEY_SECRET_ID`).
  - Logs a warning if not configured.

Planned behavior:

1. Keep current env + SecretStorage precedence.
2. If no key is found:
   - Call `getOrCreateKbApiKey()` from `@dolphin/shared/kb-auth` (or a local copy if we choose not to wire `shared` as a dependency).
   - Use `setKbApiKeyValue(key, "env")` so:
     - `defaultKbApiKey` is set.
     - `process.env.DOLPHIN_API_KEY` and `DOLPHIN_KB_API_KEY` are populated.
   - Store the key in `context.secrets` so subsequent sessions don’t hit the filesystem unnecessarily.
3. After activation, `propagateKbApiKeyToConsumers` keeps all KB-related components in sync.

Pseudocode changes:

```ts
// vscode-extension/src/extension.ts
import { getOrCreateKbApiKey } from "@dolphin/shared/kb-auth"; // or relative path if not packaged

async function initializeKbApiKey(context: vscode.ExtensionContext): Promise<void> {
  const envKey = process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY;
  if (envKey) {
    setKbApiKeyValue(envKey, "env");
    return;
  }

  const storedKey = await context.secrets.get(KB_API_KEY_SECRET_ID);
  if (storedKey) {
    setKbApiKeyValue(storedKey, "secret");
    return;
  }

  // New behavior: auto-generate per-user key (official entry point)
  try {
    const key = getOrCreateKbApiKey();
    setKbApiKeyValue(key, "env");
    await context.secrets.store(KB_API_KEY_SECRET_ID, key);
  } catch (error) {
    logger?.warn?.(
      `[Extension] Failed to initialize KB API key automatically: ${
        (error as Error).message ?? String(error)
      }`
    );
    // Leave KB API key unset; secured endpoints will reject requests until user fixes env or config.
  }
}
```

### 4.3 Agent Core Integration

**Files:**

- `agent-core/src/main.ts`
- `agent-core/src/context/context-builder.ts`
- `agent-core/src/kb/index-queue.ts`

Current:

- `AgentCoreV2` constructor creates `ContextBuilder` with:

```ts
this.contextBuilder = new ContextBuilder({
  workspaceRoot,
  kbUrl: "http://127.0.0.1:7777",
  kbApiKey: process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY,
});
```

- `ContextBuilder`’s constructor re-resolves `kbApiKey` from config or env.
- `IndexQueue` defaults `this.kbApiKey` to `kbApiKey || process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY`.

Planned changes:

1. At Agent Core process startup (`AgentCoreV2` constructor or `start()`), resolve `process.env.DOLPHIN_API_KEY` **without creating** a key:
   - Call `resolveKbApiKey({ readOnly: true })`:
     - Allows a CLI-managed key or VS Code-managed key to be used.
   - If still unset, Agent Core does **not** auto-create a key; instead, KB calls will fail with `401` until an official entry point has created the key or tests/CI provide an env override.
   - When a key is found, set both `process.env.DOLPHIN_API_KEY` and `process.env.DOLPHIN_KB_API_KEY` for internal consistency.
2. `ContextBuilder` and `IndexQueue` remain unchanged; they consume `process.env.DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY`.

Pseudocode:

```ts
// agent-core/src/main.ts
import { resolveKbApiKey } from "@dolphin/shared/kb-auth";

class AgentCoreV2 {
  constructor(workspaceRoot: string, extensionPath?: string) {
    this.workspaceRoot = workspaceRoot;
    this.extensionPath = extensionPath;

    // Ensure KB API key is available in env (read-only resolution)
    this.initializeKbApiKeyEnv();

    this.kbManager = new KBManager();
    this.mcpClient = new MCPClient();

    this.contextBuilder = new ContextBuilder({
      workspaceRoot,
      kbUrl: "http://127.0.0.1:7777",
      kbApiKey: process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY,
    });
    ...
  }

  private initializeKbApiKeyEnv() {
    const existing =
      process.env.DOLPHIN_API_KEY?.trim() || process.env.DOLPHIN_KB_API_KEY?.trim();
    if (existing) {
      return;
    }

    // Read-only resolution: Agent Core never creates the key itself
    const key = resolveKbApiKey({ readOnly: true });
    if (key) {
      process.env.DOLPHIN_API_KEY = key;
      process.env.DOLPHIN_KB_API_KEY = key;
    }
  }
}
```

### 4.4 MCP Bridge Integration

**Files:**

- `mcp-bridge/src/rest/client.ts`
- `mcp-bridge/src/util/config.ts`
- `mcp-bridge/src/cli.ts`

Current behavior:

- `CONFIG.DOLPHIN_API_URL` picks the KB base URL via env.
- `rest/client.ts` uses `doFetch()` with headers:

```ts
headers.set("Content-Type", "application/json");
headers.set("Accept", "application/json");
headers.set("X-Client", "mcp");
```

No KB API key is currently sent.

Planned behavior:

1. Add KB key resolution:
   - Use `@dolphin/shared/kb-auth`:
     - CLI entry point (`mcp-bridge/src/cli.ts`) uses `getOrCreateKbApiKey()` because it is an official key creator (for pure MCP setups without prior CLI/VSCode usage).
     - REST client (`mcp-bridge/src/rest/client.ts`) uses `resolveKbApiKey({ readOnly: true })` and never creates the key itself.
   - Env overrides (`DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY`) are respected when present.
2. In `doFetch`, add `X-API-Key` header when a key is available.

Pseudocode:

```ts
// mcp-bridge/src/rest/client.ts
import { CONFIG } from "../util/config.js";
import { resolveKbApiKey } from "@dolphin/shared/kb-auth";

let KB_API_KEY: string | undefined;

function getKbApiKey(): string | undefined {
  if (KB_API_KEY !== undefined) {
    return KB_API_KEY;
  }
  const envKey =
    process.env.DOLPHIN_API_KEY?.trim() || process.env.DOLPHIN_KB_API_KEY?.trim() || "";
  if (envKey) {
    KB_API_KEY = envKey;
    return KB_API_KEY;
  }

  KB_API_KEY = resolveKbApiKey({ readOnly: true });
  return KB_API_KEY;
}

async function doFetch<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Accept", "application/json");
  headers.set("X-Client", "mcp");

  const kbKey = getKbApiKey();
  if (kbKey) {
    headers.set("X-API-Key", kbKey);
  }

  const baseUrl = getBaseUrl();
  const res = await fetch(baseUrl + path, { ...init, headers, signal });
  ...
}
```

CLI bootstrap (`mcp-bridge/src/cli.ts`) may optionally:

- Call `resolveKbApiKey({ readOnly: true })` once and log a warning if no key is found (indicating that KB secured endpoints will reject requests).

---

## 5. Testing Strategy

### 5.1 Python Tests

New unit tests for `kb/api_key.py`:

- `test_env_override_wins()`:
  - Set `DOLPHIN_API_KEY="env-key"` and ensure `get_or_create_kb_api_key()` returns `"env-key"` without creating the file.
- `test_file_created_on_first_call()`:
  - With no env variables and no key file, call `get_or_create_kb_api_key()`.
  - Assert that:
    - The file is created.
    - The returned key matches file contents.
- `test_subsequent_calls_reuse_file()`:
  - After the file exists, multiple calls return the same key without changing the file.
- `test_race_condition_handling()`:
  - Simulate a `FileExistsError` by creating the file between two operations and ensure we still return a valid key.

Integration tests:

- Start the KB server using `uv run dolphin serve` within a temporary HOME:
  - Assert that `~/.dolphin/kb_api_key` is created.
  - Assert that `/v1/health` is public and `/v1/search` requires `X-API-Key`.

### 5.2 Node / TypeScript Tests

Shared helper `kb-auth.ts`:

- Unit tests in `shared` project:
  - Use a temporary directory for `homeDir` override.
  - Validate env override, file creation, and race behavior.

VS Code extension:

- Extend existing tests for KB lifecycle/auth:
  - Simulate activation with no env and empty SecretStorage.
  - Ensure `initializeKbApiKey` creates a key file (via mocked `os.homedir`) and calls `setKbApiKeyValue`.

Agent Core:

- Tests for `initializeKbApiKeyEnv` logic:
  - With env pre-set, no file access.
  - With no env, `resolveKbApiKey(readOnly)` finds file-based key.

MCP bridge:

- Extend `rest_client.test.ts`:
  - Confirm `X-API-Key` is set when env provides `DOLPHIN_API_KEY`.
  - Confirm `X-API-Key` is set from the key file when env is unset and file exists.

---

## 6. Migration and Backwards Compatibility

No breaking changes for existing setups:

- Users currently exporting `DOLPHIN_API_KEY` continue to work exactly as before.
- New users who run `dolphin init`, `dolphin serve`, or the VS Code extension will automatically get a per-user key file without needing to touch `.env`.
- MCP clients and Agent Core will seamlessly pick up the same key, via env or shared file, and send `X-API-Key` automatically.

Operational notes:

- We should **not** print the actual key in logs or CLI output.
- Docs should be updated to say:
  - “By default Dolphin generates and manages a KB API key under `~/.dolphin`. Environment variables `DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY` are available for advanced use (tests, CI, or remote deployments) but are not required for normal development.”

This plan provides a clear path to implementing Option 2 with minimal user friction and consistent security across all Dolphin entry points.

---

## 7. Implementation Checklist

This section is a concrete, step-by-step checklist to drive implementation. Each step should be completed (with tests) before moving to the next major block.

### 7.1 Python: KB API Key Helper and CLI Integration

1. **Add `kb/api_key.py`**
   - [ ] Create new file `kb/api_key.py`.
   - [ ] Implement:
     - [ ] `KB_API_KEY_FILENAME = "kb_api_key"`.
     - [ ] `get_kb_key_path() -> Path` returning `Path.home() / ".dolphin" / KB_API_KEY_FILENAME`.
     - [ ] Private `_env_override() -> Optional[str]` that checks `DOLPHIN_API_KEY` then `DOLPHIN_KB_API_KEY`, strips, and returns first non-empty.
     - [ ] `load_kb_api_key() -> Optional[str]`:
       - [ ] Respect `_env_override()` first.
       - [ ] If no env override, read `~/.dolphin/kb_api_key` if it exists; strip and return non-empty value; otherwise return `None`.
     - [ ] `get_or_create_kb_api_key() -> str`:
       - [ ] Respect `_env_override()` first (return without touching filesystem).
       - [ ] Ensure parent directory of `get_kb_key_path()` exists (`mkdir(parents=True, exist_ok=True)`).
       - [ ] If file exists and contains a non-empty key, return it.
       - [ ] Generate a new key via `secrets.token_hex(32)` (64 hex chars).
       - [ ] Create the file using exclusive semantics (`"x"` mode) and write the key plus newline.
       - [ ] Attempt to `chmod` to `0o600` (ignore `OSError`).
       - [ ] On `FileExistsError`, fall back to reading the file and returning its contents (or the in-memory key if empty).

2. **Wire `dolphin init` to ensure key exists**
   - [ ] In `kb/cli.py`, import `get_or_create_kb_api_key`.
   - [ ] After `kb_init(config_path)` in the `init` command:
     - [ ] Call `get_or_create_kb_api_key()` inside a `try/except` block.
     - [ ] Log (not print) a warning if key initialization fails, but do not raise—`init` should still succeed.

3. **Wire `dolphin serve` to set `DOLPHIN_API_KEY`**
   - [ ] In `kb/cli.py` `serve` command:
     - [ ] Import `os` and `get_or_create_kb_api_key`.
     - [ ] Before `uvicorn.run(...)`:
       - [ ] If neither `DOLPHIN_API_KEY` nor `DOLPHIN_KB_API_KEY` is present in `os.environ`, call `get_or_create_kb_api_key()` and set `os.environ["DOLPHIN_API_KEY"]` to the returned value.
     - [ ] Leave existing host/port behavior unchanged.

4. **(Optional) Wire `dolphin-mcp` Python wrapper (if present)**
   - [ ] If there is a Python entry point that starts the KB server on behalf of the MCP bridge, ensure it also uses `get_or_create_kb_api_key()` before spawning the server process.

5. **Python tests**
   - [ ] Add a new test module (e.g. `tests/unit/config/test_api_key.py`):
     - [ ] Use `tmp_path` / `monkeypatch` to fake `Path.home()` / `HOME` so tests don’t touch real `~/.dolphin`.
     - [ ] `test_env_override_wins`:
       - [ ] Set `DOLPHIN_API_KEY` in env, ensure `get_or_create_kb_api_key()` returns that value and no file is created.
     - [ ] `test_file_created_on_first_call`:
       - [ ] With no env and no file, call `get_or_create_kb_api_key()` and assert file exists and content matches.
     - [ ] `test_subsequent_calls_reuse_file`:
       - [ ] After first call, subsequent calls return the same key value.
     - [ ] `test_load_kb_api_key_respects_env`:
       - [ ] Env override takes precedence over file.
     - [ ] `test_load_kb_api_key_returns_none_when_missing`:
       - [ ] No env, no file → `None`.
   - [ ] Add an integration-style test for `serve` (if feasible in the existing test harness) that verifies `DOLPHIN_API_KEY` is set in the server process environment when started without an env override.

### 7.2 Node/TS: Shared Helper `shared/kb-auth.ts`

6. **Add shared Node helper**
   - [ ] Create `shared/kb-auth.ts`.
   - [ ] Implement:
     - [ ] `KbAuthOptions` with `homeDir?: string` and `readOnly?: boolean`.
     - [ ] `getKbKeyPath(opts?: KbAuthOptions): string` returning `<homeDir || os.homedir()>/'.dolphin/kb_api_key'`.
     - [ ] `resolveKbApiKey(opts?: KbAuthOptions): string | undefined`:
       - [ ] Check env (`DOLPHIN_API_KEY` then `DOLPHIN_KB_API_KEY`) and return first non-empty.
       - [ ] If no env, compute key path and:
         - [ ] If file exists, read and return its trimmed contents (or `undefined` if empty).
         - [ ] If file does not exist, return `undefined` (do not create).
     - [ ] `getOrCreateKbApiKey(opts?: KbAuthOptions): string`:
       - [ ] Respect env override first; if present, return it.
       - [ ] If file exists and non-empty, return its contents.
       - [ ] Otherwise, create directory (with `fs.mkdirSync(dir, { recursive: true })`).
       - [ ] Generate a key via `randomBytes(32).toString("hex")`.
       - [ ] Use `fs.openSync(keyPath, "wx", 0o600)` and `fs.writeFileSync` to create the file.
       - [ ] On `EEXIST`, read the file and return its contents (or the generated key as a fallback).

7. **Node/TS tests for shared helper**
   - [ ] Add tests in the `shared` package (e.g. `shared/__tests__/kb-auth.test.ts`):
     - [ ] Use a temporary directory for `homeDir` to avoid touching the real home.
     - [ ] `resolveKbApiKey` returns env override when set.
     - [ ] `resolveKbApiKey` returns `undefined` when file is missing and `readOnly` is true.
     - [ ] `getOrCreateKbApiKey` creates a file with a 64-character hex string when no env and no file.
     - [ ] `getOrCreateKbApiKey` reuses existing file contents on subsequent calls.
     - [ ] Simulate `EEXIST` by creating the file before calling helper and verify it gracefully reads the existing key.

### 7.3 VS Code Extension Integration

8. **Wire extension activation to shared helper**
   - [ ] Add dependency on `@dolphin/shared` (if not already available in the extension build).
   - [ ] In `vscode-extension/src/extension.ts`:
     - [ ] Import `getOrCreateKbApiKey` from `@dolphin/shared/kb-auth`.
     - [ ] Update `initializeKbApiKey` to:
       - [ ] Keep env check first (`DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY`).
       - [ ] Then SecretStorage check.
       - [ ] If neither yields a key, call `getOrCreateKbApiKey()` (official key creator).
       - [ ] Use `setKbApiKeyValue(key, "env")` and store in `context.secrets`.
   - [ ] Ensure `propagateKbApiKeyToConsumers` remains unchanged so the new key propagates to:
     - [ ] `DolphinViewProvider`.
     - [ ] `FileWatcher`.
     - [ ] `AutoSyncManager`.
     - [ ] `DriftDetector`.

9. **VS Code extension tests**
   - [ ] Add or extend tests to cover:
     - [ ] No env, no SecretStorage → `initializeKbApiKey` calls `getOrCreateKbApiKey` and sets internal key value.
     - [ ] Env override still respected when present.
     - [ ] SecretStorage value used when env is unset but secret exists.

### 7.4 Agent Core Integration (Read-Only)

10. **Resolve key read-only in Agent Core**

- [ ] In `agent-core/src/main.ts`:
  - [ ] Import `resolveKbApiKey` from `@dolphin/shared/kb-auth`.
  - [ ] Implement `initializeKbApiKeyEnv` (or adjust existing logic) to:
    - [ ] Check `process.env.DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY` first.
    - [ ] If not set, call `resolveKbApiKey({ readOnly: true })`.
    - [ ] If a key is found, set both `DOLPHIN_API_KEY` and `DOLPHIN_KB_API_KEY` in `process.env`.
    - [ ] Do **not** call `getOrCreateKbApiKey` from Agent Core (read-only consumer).
- [ ] Ensure `ContextBuilder` and `IndexQueue` continue to read `kbApiKey` from env/config as before.

11. **Agent Core tests**

- [ ] Add tests around `initializeKbApiKeyEnv`:
  - [ ] When env already has `DOLPHIN_API_KEY`, no file lookups are performed.
  - [ ] When env is empty but `~/.dolphin/kb_api_key` exists (simulated via `homeDir` override), env is populated with that value.
  - [ ] When neither env nor file is present, Agent Core leaves env unset (and KB requests will be rejected until an official entry point creates the key).

### 7.5 MCP Bridge Integration

12. **CLI: official key creator for pure MCP setups**

- [ ] In `mcp-bridge/src/cli.ts`:
  - [ ] Import `getOrCreateKbApiKey` from `@dolphin/shared/kb-auth`.
  - [ ] Before starting the MCP server:
    - [ ] Resolve KB API key:
      - [ ] Use env override if set.
      - [ ] Otherwise, call `getOrCreateKbApiKey()` (official key creator).
    - [ ] Set `process.env.DOLPHIN_API_KEY` (and optionally `DOLPHIN_KB_API_KEY`) to that value so the rest of the process can read it.

13. **REST client: read-only usage**

- [ ] In `mcp-bridge/src/rest/client.ts`:
  - [ ] Import `resolveKbApiKey` from `@dolphin/shared/kb-auth`.
  - [ ] Implement a module-level `getKbApiKey()` that:
    - [ ] Caches a resolved key.
    - [ ] Checks env first.
    - [ ] If env is empty, calls `resolveKbApiKey({ readOnly: true })`.
    - [ ] Never calls `getOrCreateKbApiKey`.
  - [ ] In `doFetch`, set `X-API-Key` header when `getKbApiKey()` returns a key.

14. **MCP bridge tests**

- [ ] Extend `rest_client.test.ts` to assert:
  - [ ] `X-API-Key` is set when `DOLPHIN_API_KEY` is provided.
  - [ ] `X-API-Key` is set from the shared key file when env is empty but file exists (via `homeDir` override).
- [ ] Add tests for CLI behavior:
  - [ ] When no env or file exists, `dolphin-mcp` creates the file and sets `DOLPHIN_API_KEY`.
  - [ ] When env is present, no file is created/modified.

### 7.6 Final Validation and Documentation

15. **End-to-end validation**

- [ ] On a clean dev machine (or isolated environment) with no existing `~/.dolphin`:
  - [ ] Run `uv run dolphin init` and confirm `~/.dolphin/config.toml` and `~/.dolphin/kb_api_key` are created.
  - [ ] Run `uv run dolphin serve` and confirm:
    - [ ] `/health` is reachable without auth.
    - [ ] `/v1/search` returns `401` without `X-API-Key` and succeeds when `X-API-Key` matches the file.
  - [ ] Install and activate the VS Code extension and confirm:
    - [ ] No manual API key prompts are required.
    - [ ] KB features (search, auto-sync) work without configuring env.
  - [ ] Start `dolphin-mcp` and confirm it can query the KB successfully.

16. **Docs updates**

- [ ] Update `README.md`, `vscode-extension/README.md`, and any other relevant docs to:
  - [ ] Explain that Dolphin auto-generates and manages `~/.dolphin/kb_api_key`.
  - [ ] Note that env vars `DOLPHIN_API_KEY` / `DOLPHIN_KB_API_KEY` are optional and intended for advanced use (tests/CI/remote).
- [ ] Cross-link `docs/API_KEY_PLAN.md` from architecture or security docs if helpful for maintainers.

17. **Security checklist**

- [ ] Confirm the key is never logged or surfaced in UI.
- [ ] Confirm file permissions are best-effort restrictive (`0o600` on POSIX; documented caveats on Windows).
- [ ] Confirm all KB clients now send `X-API-Key` when talking to `/v1/**` endpoints.
