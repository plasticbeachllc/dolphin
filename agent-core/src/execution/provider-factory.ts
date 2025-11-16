import type { AgentEvent } from "../../../shared/types/events";
import type { MCPClient } from "../mcp/mcp-client";
import { loadProviderSettings, type ProviderSettings } from "../utils/provider-settings";
import type { ChatProvider } from "./chat-provider";
import { AnthropicProvider, AuthManager } from "./anthropic-provider";
import { OpenAIProvider } from "./openai-provider";

export interface ProviderFactoryOptions {
  workspaceRoot: string;
  mcpClient: MCPClient;
  maxToolRounds?: number;
  onEvent?: (event: AgentEvent) => void;
  authManager?: AuthManager;
  settings?: ProviderSettings;
  defaultOpenAIModel?: string;
}

export async function createChatProvider(options: ProviderFactoryOptions): Promise<ChatProvider> {
  const settings = options.settings ?? loadProviderSettings();
  const preference = settings.provider ?? "auto";
  const authManager = options.authManager ?? new AuthManager();
  const openAIModel = settings.model ?? options.defaultOpenAIModel;

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
    ensureOpenAIKey(settings);
    return new OpenAIProvider({
      workspaceRoot: options.workspaceRoot,
      mcpClient: options.mcpClient,
      maxToolRounds: options.maxToolRounds,
      onEvent: options.onEvent,
      model: openAIModel,
      temperature: settings.temperature,
      apiKey: settings.openAIApiKey,
      baseUrl: settings.openAIBaseUrl,
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

  const hasOpenAIKey =
    settings.openAIApiKey || process.env.DOLPHIN_OPENAI_API_KEY || process.env.OPENAI_API_KEY;
  if (hasOpenAIKey) {
    return new OpenAIProvider({
      workspaceRoot: options.workspaceRoot,
      mcpClient: options.mcpClient,
      maxToolRounds: options.maxToolRounds,
      onEvent: options.onEvent,
      model: openAIModel,
      temperature: settings.temperature,
      apiKey: settings.openAIApiKey,
      baseUrl: settings.openAIBaseUrl,
    });
  }

  throw new Error(
    "No chat provider credentials found. Authenticate with Claude CLI / ANTHROPIC_API_KEY or set OPENAI_API_KEY."
  );
}

function ensureOpenAIKey(settings: ProviderSettings) {
  if (settings.openAIApiKey) {
    return;
  }
  if (process.env.DOLPHIN_OPENAI_API_KEY || process.env.OPENAI_API_KEY) {
    return;
  }
  throw new Error(
    "OpenAI provider requires OPENAI_API_KEY, DOLPHIN_OPENAI_API_KEY, or provider.openai.api_key to be set"
  );
}
