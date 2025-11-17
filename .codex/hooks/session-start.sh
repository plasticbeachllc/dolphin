#!/bin/bash
set -euo pipefail

# SessionStart hook for Dolphin project
# Installs dependencies for Python backend and TypeScript/Bun components
echo "🐬 Setting up Dolphin development environment..."
CODEX_WORKSPACE_DIR="$(git rev-parse --show-toplevel)"


# ============================================================================
# Install uv (Python package manager)
# ============================================================================
if ! command -v uv &> /dev/null; then
  echo "📦 Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
else
  echo "✅ uv already installed"
fi

# ============================================================================
# Install bun (JavaScript runtime and package manager)
# ============================================================================
if ! command -v bun &> /dev/null; then
  echo "📦 Installing bun..."
  curl -fsSL https://bun.sh/install | bash
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
  echo 'export BUN_INSTALL="$HOME/.bun"' >> "$CLAUDE_ENV_FILE"
  echo 'export PATH="$BUN_INSTALL/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
else
  echo "✅ bun already installed"
fi

# ============================================================================
# Install Python dependencies
# ============================================================================
echo "🐍 Installing Python dependencies with uv..."
cd "$CODEX_WORKSPACE_DIR"
uv sync --group test --group dev

# ============================================================================
# Install TypeScript/Bun dependencies
# ============================================================================
echo "📦 Installing agent-core dependencies..."
cd "$CODEX_WORKSPACE_DIR/agent-core"
bun install

echo "📦 Installing mcp-bridge dependencies..."
cd "$CODEX_WORKSPACE_DIR/mcp-bridge"
bun install

echo "📦 Installing shared dependencies..."
cd "$CODEX_WORKSPACE_DIR/shared"
bun install

echo "📦 Installing VSCode extension dependencies..."
cd "$CODEX_WORKSPACE_DIR/vscode-extension"
npm install

echo "📦 Installing webview dependencies..."
cd "$CODEX_WORKSPACE_DIR/vscode-extension/webview"
bun install

echo "✅ Dolphin environment setup complete!"

# ============================================================================
# Install VSCode dependencies
# ============================================================================
# sudo apt update
# sudo apt install snapd
# sudo snap install --classic code
