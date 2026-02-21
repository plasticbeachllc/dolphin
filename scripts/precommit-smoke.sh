#!/usr/bin/env bash
set -euo pipefail

# Fast smoke checks meant for pre-commit use.
uv run pytest tests/unit/api/test_api_endpoints.py -q --maxfail=1

(
  cd mcp-bridge
  bun test --serial ./src/tests/unit --bail
)

(
  cd shared
  bun test __tests__/kb-auth.test.ts ipc/__tests__/serialization.test.ts --bail
)
