import { createServer } from './mcp/server.js'

// Entry point for dev (bun run src/index.ts)
createServer().catch((err) => {
  // Avoid console; rely on file logger inside server
  process.exitCode = 1
})
