import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { tools } from "./tools/index.js";
import { initLogger, logInfo, logWarn } from "../util/logger.js";
import { CONFIG, getConfigSummary, validateConfig } from "../util/config.js";

export async function createServer(): Promise<void> {
  // Initialize file logger (no stdout pollution)
  await initLogger();

  const SERVER_NAME = CONFIG.SERVER_NAME;
  const SERVER_VERSION = CONFIG.SERVER_VERSION;
  const MCP_PROTOCOL_VERSION = CONFIG.MCP_PROTOCOL_VERSION;
  const configWarnings = validateConfig();
  await logInfo("config", "MCP config loaded", { config: getConfigSummary() });
  if (configWarnings.length > 0) {
    await logWarn("config", "MCP config warnings", { warnings: configWarnings });
  }

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
    // MCP SDK types can be extremely deep here; keep runtime behavior while avoiding TS instantiation blowups.
    const registerTool = server.registerTool.bind(server) as unknown as (
      name: string,
      meta: Record<string, unknown>,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      handler: any
    ) => void;
    registerTool(
      tool.definition.name,
      {
        title: tool.definition.annotations?.title,
        description: tool.definition.description,
        inputSchema: tool.inputSchema ?? tool.definition.inputSchema ?? {},
        annotations: tool.definition.annotations,
      },
      tool.handler
    );
  }

  // Start transport
  const transport = new StdioServerTransport();
  await server.connect(transport);

  logInfo("server_start", "MCP server started", { protocolVersion: MCP_PROTOCOL_VERSION });
}
