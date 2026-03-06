#!/usr/bin/env bash
WORKSPACE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$WORKSPACE" || true

# Python deps
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  uv sync --group dev --group test || true
fi

# JS deps
if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    if [ -f "$dir/package.json" ]; then
      (cd "$dir" && bun install --frozen-lockfile) || true
    fi
  done
fi

echo "Session maintenance complete."
