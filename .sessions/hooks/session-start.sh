#!/usr/bin/env bash
# Diagnostic log: cat /tmp/session-start.log
LOG="/tmp/session-start.log"

log() { echo "$*" >> "$LOG"; }

log "=== session-start $(date -Iseconds 2>/dev/null || date) ==="
log "uname: $(uname -sm 2>/dev/null || echo unknown)"
log "pwd: $(pwd)"
log "CLAUDE_ENV_FILE: ${CLAUDE_ENV_FILE:-<unset>}"
for cmd in curl git uv bun just node; do
  log "  $cmd: $(command -v $cmd 2>/dev/null || echo 'NOT FOUND')"
done

WORKSPACE="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$WORKSPACE" || true

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
    | tar -xz -C "$JUST_DIR" just 2>>"$LOG"; then
    export PATH="$JUST_DIR:$PATH"
    append_env "export PATH=\"$JUST_DIR:\$PATH\""
    log "just installed OK"
  else
    log "WARN: failed to install just"
  fi
fi

# Python deps
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  if uv sync --group dev --group test >>"$LOG" 2>&1; then
    log "uv sync OK"
  else
    log "WARN: uv sync failed"
  fi
fi

# JS deps
if command -v bun >/dev/null 2>&1; then
  for dir in mcp-bridge shared; do
    if [ -f "$dir/package.json" ]; then
      if (cd "$dir" && bun install) >>"$LOG" 2>&1; then
        log "bun install OK in $dir"
      else
        log "WARN: bun install failed in $dir"
      fi
    fi
  done
fi

log "=== session-start done ==="
echo "Session start complete."
