export interface ProviderAuthStatus {
  provider: string;
  authenticated: boolean;
  mode: string;
  warning?: string;
  error?: string;
}

export interface AgentAuthStatusResponse {
  providers: ProviderAuthStatus[];
}
