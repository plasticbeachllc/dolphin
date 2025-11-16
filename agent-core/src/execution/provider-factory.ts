import type { AgentEvent } from "../../../shared/types/events";
import type { MCPClient } from "../mcp/mcp-client";
import { loadProviderSettings } from "../utils/provider-settings";
import type { ChatProvider } from "./chat-provider";
import { AnthropicProvider, AuthManager } from "./anthropic-provider";
import { OpenAIProvider } from "./openai-provider";

export interface ProviderFactoryOptions {
  workspaceRoot: string;
  mcpClient: MCPClient;
  maxToolRounds?: number;
  onEvent?: (event: AgentEvent) => void;
  authManager?: AuthManager;
}

export async function createChatProvider(options: ProviderFactoryOptions): Promise<ChatProvider> {
  const settings = loadProviderSettings();
  const preference = settings.provider ?? "auto";
  const authManager = options.authManager ?? new AuthManager();

  if (preference === "anthropic") {
    return new AnthropicProvider({
      workspaceRoot: options.workspaceRoot,
      mcpClient: options.mcpClient,
      maxToolRounds: options.maxToolRounds,
      authManager,
      onEvent: options.onEvent,
      model: settings.model,
      temperature: settings.temperature,
    });
  }

  if (preference === "openai") {
    ensureOpenAIKey();
    return new OpenAIProvider({
      workspaceRoot: options.workspaceRoot,
      mcpClient: options.mcpClient,
      maxToolRounds: options.maxToolRounds,
      onEvent: options.onEvent,
      model: settings.model,
      temperature: settings.temperature,
    });
  }

  const anthropicStatus = await authManager.detectAuthStatus();
  if (anthropicStatus.authenticated) {
    return new AnthropicProvider({
      workspaceRoot: options.workspaceRoot,
      mcpClient: options.mcpClient,
      maxToolRounds: options.maxToolRounds,
      authManager,
      onEvent: options.onEvent,
      model: settings.model,
      temperature: settings.temperature,
    });
  }

  if (process.env.OPENAI_API_KEY) {
    return new OpenAIProvider({
      workspaceRoot: options.workspaceRoot,
      mcpClient: options.mcpClient,
      maxToolRounds: options.maxToolRounds,
      onEvent: options.onEvent,
      model: settings.model,
      temperature: settings.temperature,
    });
  }

  throw new Error(
    "No chat provider credentials found. Authenticate with Claude CLI / ANTHROPIC_API_KEY or set OPENAI_API_KEY."
  );
}

function ensureOpenAIKey() {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY must be set to use the OpenAI provider");
  }
}
