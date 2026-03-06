#!/usr/bin/env bash
# Log everything to file — Claude.ai swallows stdout/stderr on failure.
# After session starts: cat /tmp/session-start.log
LOG="/tmp/session-start.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== session-start $(date -Iseconds 2>/dev/null || date) ==="
echo "shell: ${BASH_VERSION:-unknown}"
echo "uname: $(uname -sm 2>/dev/null || echo unknown)"
echo "pwd:   $(pwd)"
echo "HOME:  ${HOME:-<unset>}"
echo "CLAUDE_ENV_FILE: ${CLAUDE_ENV_FILE:-<unset>}"

for cmd in curl git uv bun just node; do
  printf "  %-6s %s\n" "$cmd:" "$(command -v $cmd 2>/dev/null || echo 'NOT FOUND')"
done

WORKSPACE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$WORKSPACE" || true
echo "workspace: $WORKSPACE"

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
  echo "Installing just to $JUST_DIR ..."
  if curl -fsSL https://github.com/casey/just/releases/download/1.40.0/just-1.40.0-x86_64-unknown-linux-musl.tar.gz \
    | tar -xz -C "$JUST_DIR" just; then
    export PATH="$JUST_DIR:$PATH"
    append_env "export PATH=\"$JUST_DIR:\$PATH\""
    echo "just installed OK"
  else
    echo "WARN: failed to install just (exit $?)"
  fi
fi

# Python deps
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  echo "Running uv sync ..."
  if uv sync --group dev --group test; then
    echo "uv sync OK"
  else
    echo "WARN: uv sync failed (exit $?)"
  fi
fi

# JS deps
if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    if [ -f "$dir/package.json" ]; then
      echo "Running bun install in $dir ..."
      if (cd "$dir" && bun install); then
        echo "bun install OK in $dir"
      else
        echo "WARN: bun install failed in $dir (exit $?)"
      fi
    fi
  done
fi

echo "=== session-start done ==="
