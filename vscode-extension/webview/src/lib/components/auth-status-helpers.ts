export interface ProviderAuthStatus {
  provider: string;
  authenticated: boolean;
  mode: string;
  warning?: string;
  error?: string;
}

export function getProviderDisplayName(provider: string): string {
  switch (provider.toLowerCase()) {
    case "anthropic":
      return "Anthropic (Claude)";
    case "openai":
      return "OpenAI";
    default:
      return provider;
  }
}

export function getStatusIcon(status: ProviderAuthStatus): string {
  if (status.authenticated) {
    return "✅";
  }
  if (status.warning) {
    return "⚠️";
  }
  return "❌";
}

export function getStatusHeadline(status: ProviderAuthStatus): string {
  if (status.authenticated) {
    return status.mode === "subscription"
      ? "Using subscription benefits"
      : `Authenticated via ${status.mode}`;
  }
  if (status.error) {
    return status.error;
  }
  return "Authentication required";
}

export function getStatusHint(status: ProviderAuthStatus): string {
  if (status.authenticated) {
    return status.mode === "subscription"
      ? "Your Claude CLI subscription will be used"
      : "API billing will apply for this provider";
  }
  if (status.warning) {
    return status.warning;
  }
  return "Set an API key or authenticate via CLI";
}

export function getStatusTone(status: ProviderAuthStatus): "success" | "warning" | "danger" {
  if (status.authenticated) {
    return "success";
  }
  if (status.warning) {
    return "warning";
  }
  return "danger";
}
