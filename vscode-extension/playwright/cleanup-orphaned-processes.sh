#!/bin/bash
# Cleanup script for orphaned VSCode processes from Playwright e2e tests
# Usage: ./cleanup-orphaned-processes.sh

echo "🧹 Cleaning up orphaned VSCode processes..."

if [[ "$OSTYPE" == "darwin"* ]]; then
  # macOS
  echo "Detected macOS - using pkill"
  pkill -f "code.*--remote-debugging-port" && echo "✅ Killed VSCode processes" || echo "ℹ️  No orphaned processes found"
else
  # Linux and other Unix-like systems
  echo "Detected Linux/Unix - using pkill"
  pkill -f "code.*--remote-debugging-port" && echo "✅ Killed VSCode processes" || echo "ℹ️  No orphaned processes found"
fi

# Also clean up temporary user data directories
echo "🧹 Cleaning up temporary user data directories..."
rm -rf /tmp/dolphin-vscode-playwright-* && echo "✅ Cleaned temp directories" || echo "ℹ️  No temp directories to clean"

echo "✨ Cleanup complete!"
