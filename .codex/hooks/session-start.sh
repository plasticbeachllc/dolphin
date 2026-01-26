#!/usr/bin/env bash
set -euo pipefail

echo "Initializing 🐬 dolphin development environment..."
CODEX_WORKSPACE_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$CODEX_WORKSPACE_DIR"

ENV_FILE="${CODEX_ENV_FILE:-${CLAUDE_ENV_FILE:-}}"
append_env() {
  if [ -n "${ENV_FILE}" ]; then
    echo "$1" >> "$ENV_FILE"
  fi
}

if [ -d "$HOME/.local/bin" ]; then
  export PATH="$HOME/.local/bin:$PATH"
  append_env 'export PATH="$HOME/.local/bin:$PATH"'
fi

if [ -d "$HOME/.bun/bin" ]; then
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
  append_env 'export BUN_INSTALL="$HOME/.bun"'
  append_env 'export PATH="$BUN_INSTALL/bin:$PATH"'
fi

if command -v uv >/dev/null 2>&1; then
  if [ -f "pyproject.toml" ]; then
    uv sync --group dev --group test
  fi
else
  echo "uv not found; skipping Python deps."
fi

if command -v bun >/dev/null 2>&1; then
  if [ -f "agent-core/package.json" ]; then
    (cd "agent-core" && bun install)
  fi
  if [ -f "mcp-bridge/package.json" ]; then
    (cd "mcp-bridge" && bun install)
  fi
else
  echo "bun not found; skipping JS deps."
fi

echo "Codex session start complete."
