#!/usr/bin/env bash
WORKSPACE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$WORKSPACE" || exit 0

append_env() { [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "$1" >> "$CLAUDE_ENV_FILE" || true; }

# Add tool paths
for p in "$HOME/.local/bin" "$HOME/.bun/bin"; do
  [ -d "$p" ] && export PATH="$p:$PATH" && append_env "export PATH=\"$p:\$PATH\""
done

# Install just if missing
if ! command -v just >/dev/null 2>&1; then
  mkdir -p "$HOME/.local/bin"
  curl -fsSL https://github.com/casey/just/releases/download/1.40.0/just-1.40.0-x86_64-unknown-linux-musl.tar.gz \
    | tar -xz -C "$HOME/.local/bin" just 2>/dev/null || true
  export PATH="$HOME/.local/bin:$PATH"
  append_env "export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# Python deps
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  uv sync --group dev --group test 2>/dev/null || true
fi

# JS deps
if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    [ -f "$dir/package.json" ] && (cd "$dir" && bun install 2>/dev/null) || true
  done
fi
