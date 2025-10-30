#!/usr/bin/env bash
claude mcp add pb-kb --transport stdio -e "OPENAI_API_KEY=${OPENAI_API_KEY}" -- bun run /Users/tdc/worktable/dolphin/mcp-bridge/src/index.ts
