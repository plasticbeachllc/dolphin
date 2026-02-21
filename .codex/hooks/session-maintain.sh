#!/usr/bin/env bash
set -euo pipefail

echo "Codex maintenance: minimal refresh"
CODEX_WORKSPACE_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$CODEX_WORKSPACE_DIR"

if command -v uv >/dev/null 2>&1; then
  if [ -f "pyproject.toml" ]; then
    uv sync --group dev --group test
  fi
else
  echo "uv not found; skipping Python refresh."
fi

if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    if [ -f "$dir/package.json" ]; then
      (cd "$dir" && bun install --no-save)
    fi
  done
else
  echo "bun not found; skipping JS refresh."
fi

echo "Codex maintenance complete."
