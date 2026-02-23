#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$WORKSPACE"

# Python deps
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  uv sync --group dev --group test
fi

# JS deps
if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    [ -f "$dir/package.json" ] && (cd "$dir" && bun install --no-save)
  done
fi

echo "Session maintenance complete."
