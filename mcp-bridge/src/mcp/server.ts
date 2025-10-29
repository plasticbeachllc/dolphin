import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { tools } from './tools/index.js'
import { initLogger, logInfo } from '../util/logger.js'

export async function createServer (): Promise<void> {
  // Initialize file logger (no stdout pollution)
  await initLogger()

  const server = new Server({
    name: 'pb-kb-mcp',
    version: '0.2.0',
    capabilities: {
      tools: { listChanged: false },
      logging: {}
    }
  })

  // Register tools
  for (const tool of tools) {
    server.tool(tool.definition, tool.handler)
  }

  // Start transport
  const transport = new StdioServerTransport()
  await server.connect(transport)

  logInfo('server_start', 'MCP server started', { protocolVersion: '2025-06-18' })
}
