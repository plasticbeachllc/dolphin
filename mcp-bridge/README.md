# PB KB MCP Bridge (Phase 5)

Status: Sprint 1 (v0.2.0)

Run (dev)
- bun run mcp-bridge/src/index.ts

Build
- bun x tsc -p mcp-bridge/tsconfig.json

Run (bin)
- mcp-bridge/dist/cli.js (shebang uses bun)

Configure in Continue
- serverCommand: mcp-bridge/dist/cli.js
  - For dev: serverCommand: bun, args: ["run", "mcp-bridge/src/index.ts"]

Logs
- File: mcp-bridge/logs/mcp.log
- Rotation: 5 MB, keep 3 files (mcp.log.1..3)

Tests
- Unit: bun test (uses mock REST server)
- Integration: run retriever REST service on 127.0.0.1:7777, then run tools manually or adapt tests

Spec
- See docs/phase-5-mcp-bridge-spec.md
