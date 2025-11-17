import type { ProviderAuthStatus } from "../../../shared/types/events";
import type { ChatProvider } from "../execution/chat-provider";

export async function buildProviderAuthStatuses(
  providers: ChatProvider[]
): Promise<ProviderAuthStatus[]> {
  const statuses: ProviderAuthStatus[] = [];

  for (const provider of providers) {
    const metadata = provider.getProviderMetadata();
    const authStatus = await provider.detectAuthStatus();
    statuses.push({
      provider: metadata.provider,
      authenticated: authStatus.authenticated,
      mode: authStatus.mode,
      warning: authStatus.warning,
      error: authStatus.error,
    });
  }

  return statuses;
}
