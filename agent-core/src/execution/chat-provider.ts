import type { AgentEvent } from "../../../shared/types/events";
import type { ToolExecutorMessage, UsageStats } from "../llm/tool-executor";

export interface AuthStatus {
  authenticated: boolean;
  mode: "subscription" | "api_key" | "none" | string;
  source?: string;
  warning?: string;
  error?: string;
}

export interface ExecuteParams {
  message: string;
  conversationHistory?: Array<{ role: "user" | "assistant"; content: string }>;
  onEvent?: (event: AgentEvent) => void;
}

export interface ExecuteResult {
  messages: ToolExecutorMessage[];
  stopReason?: string;
  toolRounds: number;
  usage: UsageStats;
}

export interface ChatProvider {
  initialize(): Promise<void>;
  execute(params: ExecuteParams): Promise<ExecuteResult>;
  abort(): void;
  detectAuthStatus(): Promise<AuthStatus>;
  ensureAuthenticated(): Promise<void>;
  getUsage(): UsageStats;
  getProviderMetadata(): { provider: string; model: string; baseUrl?: string };
}
