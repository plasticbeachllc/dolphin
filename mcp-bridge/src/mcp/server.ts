import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { tools } from "./tools/index.js";
import { initLogger, logInfo } from "../util/logger.js";
import { CONFIG } from "../util/config.js";

export async function createServer(): Promise<void> {
  // Initialize file logger (no stdout pollution)
  await initLogger();

  const SERVER_NAME = CONFIG.SERVER_NAME;
  const SERVER_VERSION = CONFIG.SERVER_VERSION;

  const server = new McpServer(
    {
      name: SERVER_NAME,
      version: SERVER_VERSION,
    },
    {
      capabilities: {
        tools: { listChanged: false },
        logging: {},
      },
    }
  );

  // Register tools
  for (const tool of tools) {
    server.registerTool(
      tool.definition.name,
      {
        title: tool.definition.annotations?.title,
        description: tool.definition.description,
        inputSchema: tool.inputSchema,
        annotations: tool.definition.annotations,
      },
      tool.handler
    );
  }

  // Start transport
  const transport = new StdioServerTransport();
  await server.connect(transport);

  logInfo("server_start", "MCP server started", { protocolVersion: "2025-06-18" });
}
