import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { tools, type ToolHandler } from "./tools/index.js";
import { initLogger, logInfo, logWarn } from "../util/logger.js";
import { CONFIG, getConfigSummary, validateConfig } from "../util/config.js";

/** Shape of a tool entry as used during registration. */
interface ToolEntry {
  definition: { name: string; description?: string; annotations?: Record<string, unknown> };
  inputSchema?: Record<string, unknown>;
  handler: ToolHandler;
}

/** Dependency overrides for testing. All fields optional; defaults to real modules. */
export interface CreateServerDeps {
  config?: { SERVER_NAME: string; SERVER_VERSION: string; MCP_PROTOCOL_VERSION: string };
  getConfigSummary?: () => unknown;
  validateConfig?: () => string[];
  initLogger?: () => Promise<void>;
  logInfo?: (...args: unknown[]) => unknown;
  logWarn?: (...args: unknown[]) => unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- MCP SDK generics are too deep for TS to infer
  McpServerClass?: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- MCP SDK transport generics are too deep for TS to infer
  TransportClass?: any;
  toolList?: ToolEntry[];
}

export async function createServer(deps: CreateServerDeps = {}): Promise<void> {
  const cfg = deps.config ?? CONFIG;
  const cfgSummary = deps.getConfigSummary ?? getConfigSummary;
  const cfgValidate = deps.validateConfig ?? validateConfig;
  const _initLogger = deps.initLogger ?? initLogger;
  const _logInfo = deps.logInfo ?? logInfo;
  const _logWarn = deps.logWarn ?? logWarn;
  const Server = deps.McpServerClass ?? McpServer;
  const Transport = deps.TransportClass ?? StdioServerTransport;
  const _tools = deps.toolList ?? tools;

  // Initialize file logger (no stdout pollution)
  await _initLogger();

  const SERVER_NAME = cfg.SERVER_NAME;
  const SERVER_VERSION = cfg.SERVER_VERSION;
  const MCP_PROTOCOL_VERSION = cfg.MCP_PROTOCOL_VERSION;
  const configWarnings = cfgValidate();
  await _logInfo("config", "MCP config loaded", { config: cfgSummary() });
  if (configWarnings.length > 0) {
    await _logWarn("config", "MCP config warnings", { warnings: configWarnings });
  }

  const server = new Server(
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
  for (const tool of _tools) {
    // Runtime guard: skip malformed tool entries that would crash registerTool.
    if (!tool.definition?.name || typeof tool.handler !== "function") {
      await _logWarn(
        "tool_register",
        `Skipping malformed tool: ${JSON.stringify(tool.definition?.name)}`
      );
      continue;
    }
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
        inputSchema: tool.inputSchema ?? {},

        annotations: tool.definition.annotations,
      },
      tool.handler
    );
  }

  // Start transport
  const transport = new Transport();
  await server.connect(transport);

  await _logInfo("server_start", "MCP server started", { protocolVersion: MCP_PROTOCOL_VERSION });
}
