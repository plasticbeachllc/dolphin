#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$WORKSPACE"

# Claude Code sets CLAUDE_ENV_FILE for SessionStart hooks; write exports there
# to persist env vars across the session.
append_env() { [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "$1" >> "$CLAUDE_ENV_FILE"; }

# Expose common tool paths
for p in "$HOME/.local/bin" "$HOME/.bun/bin"; do
  if [ -d "$p" ]; then
    export PATH="$p:$PATH"
    append_env "export PATH=\"$p:\$PATH\""
  fi
done

# Python deps
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  uv sync --group dev --group test
fi

# JS deps
if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    [ -f "$dir/package.json" ] && (cd "$dir" && bun install)
  done
fi

echo "Session start complete."
