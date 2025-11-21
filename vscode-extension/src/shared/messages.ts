import type { AgentEvent } from "../types/events";
import type { AgentAuthStatusResponse } from "../types/auth";
import type { ProviderId, ProviderModelOption } from "../config/provider-options";

export interface ThemeUpdateMessage {
  type: "theme_update";
  theme: {
    kind: "dark" | "light";
    colors: Record<string, string>;
  };
}

export interface AuthStatusMessage {
  type: "auth_status";
  status: AgentAuthStatusResponse;
}

export interface KbResponseMessage {
  type:
    | "kb_register_repo_response"
    | "kb_get_stats_response"
    | "kb_trigger_reindex_response"
    | "kb_get_status_response"
    | "kb_clear_index_response";
  requestId?: string;
  data?: unknown;
  error?: string;
}

export interface SecretStatusMessage {
  type: "secretStatus";
  provider: ProviderId;
  ok: boolean;
  message?: string;
}

export interface SettingsSaveMessage {
  type: "settings.save";
  provider: ProviderId;
  anthropicModel: string;
  openaiModel: string;
}

export interface SettingsSavedMessage {
  type: "settings.saved";
  provider: ProviderId;
  model: string;
  anthropicModel: string;
  openaiModel: string;
}

export interface SettingsErrorMessage {
  type: "settings.error";
  provider: ProviderId;
  code: "missingSecret" | "unknown";
  message: string;
}

export interface GetProviderSettingsCommand {
  type: "get_provider_settings";
}

export interface ProviderSettingsMessage {
  type: "provider_settings";
  currentProvider: ProviderId;
  currentModel: string;
  availableProviders: {
    id: ProviderId;
    label: string;
    description: string;
    models: ProviderModelOption[];
  }[];
}

export interface SaveProviderSettingsCommand {
  type: "save_provider_settings";
  provider: ProviderId;
  model: string;
}


export type ExtensionToWebviewMessage =
  | AgentEvent
  | ThemeUpdateMessage
  | AuthStatusMessage
  | KbResponseMessage
  | SecretStatusMessage
  | SettingsSavedMessage
  | SettingsErrorMessage
  | ProviderSettingsMessage;

export interface SendMessageCommand {
  type: "send_message";
  content: string;
  mode?: "code" | "architect";
  timestamp?: number;
}

export interface ApplyDiffCommand {
  type: "apply_diff";
  diff?: Record<string, unknown>;
}

export interface ConversationCommand {
  type: "list_conversations" | "clear_conversation";
}

export interface ConversationLoadCommand {
  type: "load_conversation";
  conversationId: string;
}

export interface ConversationDeleteCommand {
  type: "delete_conversation";
  conversationId: string;
}

export interface ConversationRenameCommand {
  type: "rename_conversation";
  conversationId: string;
  newTitle: string;
}

export interface KbRegisterRepoCommand {
  type: "kb_register_repo";
  name: string;
  path: string;
  default_embed_model?: string;
  requestId?: string;
}

export interface KbGetStatsCommand {
  type: "kb_get_stats";
  repoName: string;
  requestId?: string;
}

export interface KbTriggerReindexCommand {
  type: "kb_trigger_reindex";
  repoName: string;
  request?: Record<string, unknown>;
  requestId?: string;
}

export interface KbGetStatusCommand {
  type: "kb_get_status";
  taskId: string;
  requestId?: string;
}

export interface KbClearIndexCommand {
  type: "kb_clear_index";
  repoName: string;
  confirmed: boolean;
  requestId?: string;
}

export interface SecretCommand {
  type: "setSecret";
  provider: ProviderId;
}

export interface OpenFileCommand {
  type: "open_file";
  path: string;
}

export type WebviewToExtensionMessage =
  | { type: "webview_loaded" }
  | SendMessageCommand
  | { type: "abort_generation" }
  | { type: "get_auth_status" }
  | ApplyDiffCommand
  | ConversationCommand
  | ConversationLoadCommand
  | ConversationDeleteCommand
  | ConversationRenameCommand
  | KbGetStatusCommand
  | KbRegisterRepoCommand
  | KbGetStatsCommand
  | KbTriggerReindexCommand
  | KbClearIndexCommand
  | { type: "check_dolphin_config" }
  | { type: "dolphin_init" }
  | SecretCommand
  | SettingsSaveMessage
  | OpenFileCommand
  | GetProviderSettingsCommand
  | SaveProviderSettingsCommand;
