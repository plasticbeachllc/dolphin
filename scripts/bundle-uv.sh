#!/bin/bash
# Bundle uv binaries for all platforms into VSCode extension

set -e

DIST_DIR="vscode-extension/dist/uv"
UV_VERSION="0.5.11"  # Latest stable version

echo "🐬 Bundling uv binaries for VSCode extension..."
echo "Version: ${UV_VERSION}"

# Create dist directory
mkdir -p "${DIST_DIR}"

# Download uv for all platforms
echo ""
echo "📥 Downloading uv binaries..."

# macOS ARM64
echo "  → darwin-arm64"
curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-aarch64-apple-darwin.tar.gz" | \
  tar xz -C "${DIST_DIR}"
mv "${DIST_DIR}/uv-aarch64-apple-darwin/uv" "${DIST_DIR}/uv-darwin-arm64"
rm -rf "${DIST_DIR}/uv-aarch64-apple-darwin"

# macOS x64
echo "  → darwin-x64"
curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-apple-darwin.tar.gz" | \
  tar xz -C "${DIST_DIR}"
mv "${DIST_DIR}/uv-x86_64-apple-darwin/uv" "${DIST_DIR}/uv-darwin-x64"
rm -rf "${DIST_DIR}/uv-x86_64-apple-darwin"

# Linux x64
echo "  → linux-x64"
curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" | \
  tar xz -C "${DIST_DIR}"
mv "${DIST_DIR}/uv-x86_64-unknown-linux-gnu/uv" "${DIST_DIR}/uv-linux-x64"
rm -rf "${DIST_DIR}/uv-x86_64-unknown-linux-gnu"

# Windows x64
echo "  → win32-x64"
curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-pc-windows-msvc.zip" -o uv-win.zip
unzip -q -j uv-win.zip -d "${DIST_DIR}"
mv "${DIST_DIR}/uv.exe" "${DIST_DIR}/uv-win32-x64.exe"
rm -f "${DIST_DIR}/uvx.exe"  # Remove uvx, we only need uv
rm uv-win.zip

# Make binaries executable on Unix
chmod +x "${DIST_DIR}/uv-darwin-arm64"
chmod +x "${DIST_DIR}/uv-darwin-x64"
chmod +x "${DIST_DIR}/uv-linux-x64"

echo ""
echo "✅ uv binaries bundled successfully:"
ls -lh "${DIST_DIR}"

echo ""
echo "Total size: $(du -sh ${DIST_DIR} | cut -f1)"