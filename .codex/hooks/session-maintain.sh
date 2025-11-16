#!/bin/bash
set -euo pipefail

echo "🧹 Running Dolphin maintenance..."

cd "$CODEX_WORKSPACE_DIR"

# ============================================================================
# Keep local clone fresh (if applicable)
# ============================================================================
echo "🔄 Updating git repo..."
git fetch origin || true
git checkout develop || true
git pull --ff-only origin develop || true

# ============================================================================
# Tool self-updates
# ============================================================================
echo "⬆️ Updating uv..."
uv self update || true

echo "⬆️ Updating bun..."
bun upgrade || true

# ============================================================================
# Dependency refresh (lockfile-respecting)
# ============================================================================
echo "🐍 Refreshing Python dependencies..."
uv sync --group dev --group test

echo "📦 Refreshing JS/Bun dependencies..."
cd "$CODEX_WORKSPACE_DIR/agent-core"
bun install --no-save

cd "$CODEX_WORKSPACE_DIR/mcp-bridge"
bun install --no-save

cd "$CODEX_WORKSPACE_DIR/shared"
bun install --no-save

cd "$CODEX_WORKSPACE_DIR/vscode-extension"
npm install --no-fund --no-audit

cd "$CODEX_WORKSPACE_DIR/vscode-extension/webview"
bun install --no-save

# ============================================================================
# Cleanup caches & build artifacts
# ============================================================================
echo "🧽 Cleaning caches and build artifacts..."
cd "$CODEX_WORKSPACE_DIR"

find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name ".pytest_cache" -type d -prune -exec rm -rf {} +
rm -rf .mypy_cache dist build

uv cache prune || true
bun pm cache rm || true
npm cache clean --force || true

echo "🎯 Dolphin maintenance complete."
