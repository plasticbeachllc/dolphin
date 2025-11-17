<script lang="ts">
  import { onMount } from 'svelte';
  import { Badge } from '$lib/components/ui/badge';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { getVSCodeAPI } from '$lib/api/vscode';
  import {
    type ProviderAuthStatus,
    getProviderDisplayName,
    getStatusHeadline,
    getStatusHint,
    getStatusIcon,
    getStatusTone
  } from './auth-status-helpers';

  interface AuthStatusPayload {
    providers: ProviderAuthStatus[];
  }

  let providerStatuses = $state<ProviderAuthStatus[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let lastUpdated = $state<string | null>(null);
  
  onMount(async () => {
    await fetchAuthStatus();
  });
  
  async function fetchAuthStatus() {
    try {
      loading = true;
      error = null;
      
      // Use the singleton VSCode API
      const vscode = getVSCodeAPI();
      const handleMessage = (event: MessageEvent) => {
        const message = event.data as { type?: string; status?: AuthStatusPayload };
        if (message.type === 'auth_status') {
          providerStatuses = message.status?.providers ?? [];
          lastUpdated = new Date().toLocaleTimeString();
          loading = false;
          clearTimeout(timeout);
          window.removeEventListener('message', handleMessage);
        }
      };

      window.addEventListener('message', handleMessage);
      vscode.postMessage({ type: 'get_auth_status' });

      const timeout = setTimeout(() => {
        if (loading) {
          error = 'Failed to fetch auth status';
          loading = false;
          window.removeEventListener('message', handleMessage);
        }
      }, 5000);
    } catch (err: any) {
      error = err.message;
      loading = false;
    }
  }

  function getBadgeVariant(status: ProviderAuthStatus): 'default' | 'secondary' | 'destructive' {
    const tone = getStatusTone(status);
    if (tone === 'success') return 'default';
    if (tone === 'warning') return 'secondary';
    return 'destructive';
  }
</script>

<Card>
  <CardHeader>
    <CardTitle>Authentication Status</CardTitle>
    <CardDescription>Current Anthropic / OpenAI configuration</CardDescription>
  </CardHeader>
  <CardContent>
    {#if loading}
      <div class="flex items-center space-x-2">
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
        <p class="text-sm text-muted-foreground">Checking authentication...</p>
      </div>
    {:else if error}
      <div class="rounded-md bg-destructive/10 p-3">
        <p class="text-sm text-destructive">❌ {error}</p>
      </div>
    {:else}
      <div class="space-y-4">
        {#if providerStatuses.length === 0}
          <div class="rounded-md bg-secondary/30 p-3">
            <p class="text-sm text-muted-foreground">
              Provider configuration unavailable. Set a provider and API key in VS Code settings to
              see detailed status.
            </p>
          </div>
        {:else}
          {#each providerStatuses as status (status.provider)}
            <div class="rounded-md border p-3 space-y-2">
              <div class="flex items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                  <span class="text-2xl">{getStatusIcon(status)}</span>
                  <div>
                    <p class="font-medium">{getProviderDisplayName(status.provider)}</p>
                    <p class="text-xs text-muted-foreground">{getStatusHeadline(status)}</p>
                  </div>
                </div>
                <Badge variant={getBadgeVariant(status)}>
                  {status.authenticated ? 'Authenticated' : 'Action Required'}
                </Badge>
              </div>
              <p class="text-xs text-muted-foreground">{getStatusHint(status)}</p>
            </div>
          {/each}
        {/if}

        {#if lastUpdated}
          <p class="text-xs text-muted-foreground">Last updated: {lastUpdated}</p>
        {/if}

        <button
          onclick={() => fetchAuthStatus()}
          class="text-sm text-muted-foreground hover:text-foreground underline"
        >
          Refresh status
        </button>
      </div>
    {/if}
  </CardContent>
</Card>