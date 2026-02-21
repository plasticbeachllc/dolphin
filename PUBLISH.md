## Release Process

Dolphin is a monorepo with independently versioned release components:

- Python package (`py-v*`)
- MCP bridge (`mcp-v*`)

## Tag prefixes

- Python: `py-vX.Y.Z`
- MCP bridge: `mcp-vX.Y.Z`

## Python package (`py-v*`)

```bash
# Update version in pyproject.toml
uv run pytest tests/unit/ tests/integration/

git tag py-v0.2.1
git push origin py-v0.2.1
```

This triggers `.github/workflows/publish-kb.yml`.

## MCP bridge (`mcp-v*`)

```bash
# Update version in mcp-bridge/package.json
cd mcp-bridge && bun test

git tag mcp-v0.2.3
git push origin mcp-v0.2.3
```

This triggers `.github/workflows/publish-mcp.yml`.

## Recommended flow

```bash
git checkout develop
# update versions + tests
git commit -am "chore: bump release versions"
git push origin develop

git checkout main
git merge develop
git push origin main

git tag py-v0.2.1 mcp-v0.2.3
git push origin --tags
```

## Manual publishing

### Python

```bash
uv build
uv publish
```

### MCP bridge

```bash
cd mcp-bridge
bun install
bun run build
bun publish --access public
```

## Version guidelines

- Patch (`0.0.x`): bug fixes
- Minor (`0.x.0`): additive features
- Major (`x.0.0`): breaking changes

Tags must match the version in package files or publish workflows fail.
