## Release Process

Dolphin is a monorepo with independently versioned components. Each component (Python package, VSCode extension, MCP bridge) has its own release cadence and version number.

### Independent Release Workflow

Each component is released independently using Git tags with prefixes:

#### 1. Python Package (`py-v*`)

```bash
# Update version in pyproject.toml
# Run tests
uv run pytest

# Create and push tag
git tag py-v0.1.14
git push origin py-v0.1.14
```

This triggers the [`publish-kb.yml`](.github/workflows/publish-kb.yml:1) workflow which:

- Builds the package with `uv build`
- Publishes to PyPI using trusted publishing

**Setup Required**: Configure trusted publishing in PyPI project settings or add `PYPI_API_TOKEN` secret.

#### 2. VSCode Extension (`vscode-v*`)

```bash
# Update version in vscode-extension/package.json
# Test extension locally

# Create and push tag
git tag vscode-v0.1.1
git push origin vscode-v0.1.1
```

This triggers the [`publish-vscode.yml`](.github/workflows/publish-vscode.yml:1) workflow which:

- Installs dependencies with npm
- Builds webview with Bun
- Publishes to VS Code Marketplace

**Setup Required**: Add `VSCE_TOKEN` (Visual Studio Marketplace Personal Access Token) to repository secrets.

#### 3. MCP Bridge (`mcp-v*`)

```bash
# Update version in mcp-bridge/package.json
# Run tests
cd mcp-bridge && bun test

# Create and push tag
git tag mcp-v0.1.3
git push origin mcp-v0.1.3
```

This triggers the [`publish-mcp.yml`](.github/workflows/publish-mcp.yml:1) workflow which:

- Installs dependencies with Bun
- Builds package
- Publishes to npm registry

**Setup Required**: Add `NPM_TOKEN` to repository secrets.

### Git Flow Integration

The workflows trigger on **git tags**, not branches. Here's the complete Git Flow process:

#### Daily Development

```bash
# Start feature
git flow feature start my-feature

# Work on feature...
# Commit changes

# Finish feature (merges to develop)
git flow feature finish my-feature
git push origin develop
```

#### Releasing Components

**Step 1: Prepare on develop branch**

```bash
# On develop branch
git checkout develop

# Update version(s) in package files
# - pyproject.toml for Python
# - vscode-extension/package.json for VSCode
# - mcp-bridge/package.json for MCP

# Commit version bumps
git add pyproject.toml vscode-extension/package.json mcp-bridge/package.json
git commit -m "chore: bump version(s) for release"
git push origin develop
```

**Step 2: Merge to main**

```bash
# Merge develop to main
git checkout main
git merge develop
git push origin main
```

**Step 3: Create tags (triggers workflows)**

```bash
# IMPORTANT: You must be on main branch when creating tags
git checkout main

# Tag only the component(s) you want to release
git tag py-v0.1.14      # Triggers Python package publish
git tag vscode-v0.1.1   # Triggers VSCode extension publish
git tag mcp-v0.1.3      # Triggers MCP bridge publish

# Push tags - this triggers the GitHub Actions workflows
git push origin --tags
```

**The branch doesn't matter for triggering** - workflows trigger on tags being pushed to the repository. However, **best practice is to tag from main** to ensure you're releasing production-ready code.

#### Quick Reference

```bash
# Complete release flow
git checkout develop
# ... update versions, commit ...
git push origin develop

git checkout main
git merge develop
git push origin main

git tag py-v0.1.14      # Tag what changed
git push origin --tags  # Triggers workflows
```

**Multiple components?** You can create multiple tags and push them all at once:

```bash
git tag py-v0.1.14 vscode-v0.1.1 mcp-v0.1.3
git push origin --tags
# All three workflows run in parallel
```

### Manual Publishing

If you need to publish manually without GitHub Actions:

**Python Package:**

```bash
uv build
uv publish
```

**VSCode Extension:**

```bash
cd vscode-extension
npm install
cd webview && bun install && bun run build && cd ..
npx vsce publish --pat <your-pat>
```

**MCP Bridge:**

```bash
cd mcp-bridge
bun install
bun run build
npm publish --access public
```

### Version Bump Guidelines

- **Patch** (0.0.x): Bug fixes, minor changes
- **Minor** (0.x.0): New features, non-breaking changes
- **Major** (x.0.0): Breaking API changes

Components can be versioned independently based on their actual changes.

**Version/tag alignment:** ensure the tag (e.g. `py-v0.2.0`) matches the component version in its package file, or the publish workflows will fail fast.
