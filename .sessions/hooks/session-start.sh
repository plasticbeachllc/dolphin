#!/usr/bin/env bash
set -uo pipefail

WORKSPACE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$WORKSPACE"

# Claude Code sets CLAUDE_ENV_FILE for SessionStart hooks; write exports there
# to persist env vars across the session.
append_env() { [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "$1" >> "$CLAUDE_ENV_FILE" || true; }

# Expose common tool paths
for p in "$HOME/.local/bin" "$HOME/.bun/bin"; do
  if [ -d "$p" ]; then
    export PATH="$p:$PATH"
    append_env "export PATH=\"$p:\$PATH\""
    if [[ "$p" == *"/.bun/bin" ]]; then
      export BUN_INSTALL="$HOME/.bun"
      append_env 'export BUN_INSTALL="$HOME/.bun"'
    fi
  fi
done

# Install just if missing
if ! command -v just >/dev/null 2>&1; then
  JUST_DIR="$HOME/.local/bin"
  mkdir -p "$JUST_DIR"
  if curl -fsSL https://github.com/casey/just/releases/download/1.40.0/just-1.40.0-x86_64-unknown-linux-musl.tar.gz \
    | tar -xz -C "$JUST_DIR" just 2>/dev/null; then
    export PATH="$JUST_DIR:$PATH"
    append_env "export PATH=\"$JUST_DIR:\$PATH\""
  else
    echo "Warning: failed to install just" >&2
  fi
fi

# Python deps
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  uv sync --group dev --group test || echo "Warning: uv sync failed" >&2
fi

# JS deps
if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    if [ -f "$dir/package.json" ]; then
      (cd "$dir" && bun install) || echo "Warning: bun install failed in $dir" >&2
    fi
  done
fi

echo "Session start complete."
