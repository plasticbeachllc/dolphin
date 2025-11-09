<script lang="ts">
  import { onMount } from 'svelte';
  import { Badge } from '$lib/components/ui/badge';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { getVSCodeAPI } from '$lib/api/vscode';
  
  interface AuthStatusData {
    mode: 'claude_cli' | 'api_key' | 'auto';
    cliInstalled: boolean;
    cliAuthenticated: boolean;
    apiKeySet: boolean;
    willUseSubscription: boolean;
  }
  
  let authStatus = $state<AuthStatusData | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  
  onMount(async () => {
    await fetchAuthStatus();
  });
  
  async function fetchAuthStatus() {
    try {
      loading = true;
      error = null;
      
      // Use the singleton VSCode API
      const vscode = getVSCodeAPI();
      vscode.postMessage({
        type: 'get_auth_status'
      });
      
      // Listen for response
      const handleMessage = (event: MessageEvent) => {
        const message = event.data;
        if (message.type === 'auth_status') {
          authStatus = message.status;
          loading = false;
          window.removeEventListener('message', handleMessage);
        }
      };
      
      window.addEventListener('message', handleMessage);
      
      // Timeout after 5 seconds
      setTimeout(() => {
        if (loading) {
          error = 'Failed to fetch auth status';
          loading = false;
        }
      }, 5000);
    } catch (err: any) {
      error = err.message;
      loading = false;
    }
  }
  
  function getStatusColor(status: AuthStatusData): string {
    if (status.willUseSubscription) return 'bg-green-500';
    if (status.apiKeySet) return 'bg-blue-500';
    return 'bg-yellow-500';
  }
  
  function getStatusText(status: AuthStatusData): string {
    if (status.willUseSubscription) return 'Using Claude Subscription';
    if (status.apiKeySet) return 'Using API Key';
    if (status.cliInstalled && !status.cliAuthenticated) return 'CLI Not Authenticated';
    if (!status.cliInstalled && !status.apiKeySet) return 'Not Configured';
    return 'Auto-detecting...';
  }
  
  function getStatusIcon(status: AuthStatusData): string {
    if (status.willUseSubscription) return '✅';
    if (status.apiKeySet) return '💳';
    if (status.cliInstalled && !status.cliAuthenticated) return '⚠️';
    return '❌';
  }
</script>

<Card>
  <CardHeader>
    <CardTitle>Authentication Status</CardTitle>
    <CardDescription>Current Claude AI configuration</CardDescription>
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
    {:else if authStatus}
      <div class="space-y-4">
        <!-- Status Badge -->
        <div class="flex items-center space-x-2">
          <span class="text-2xl">{getStatusIcon(authStatus)}</span>
          <div>
            <p class="font-medium">{getStatusText(authStatus)}</p>
            <p class="text-xs text-muted-foreground">Mode: {authStatus.mode}</p>
          </div>
        </div>
        
        <!-- Details -->
        <div class="space-y-2 text-sm">
          <div class="flex items-center justify-between">
            <span class="text-muted-foreground">CLI Installed:</span>
            <Badge variant={authStatus.cliInstalled ? 'default' : 'secondary'}>
              {authStatus.cliInstalled ? 'Yes' : 'No'}
            </Badge>
          </div>
          
          <div class="flex items-center justify-between">
            <span class="text-muted-foreground">CLI Authenticated:</span>
            <Badge variant={authStatus.cliAuthenticated ? 'default' : 'secondary'}>
              {authStatus.cliAuthenticated ? 'Yes' : 'No'}
            </Badge>
          </div>
          
          <div class="flex items-center justify-between">
            <span class="text-muted-foreground">API Key Set:</span>
            <Badge variant={authStatus.apiKeySet ? 'default' : 'secondary'}>
              {authStatus.apiKeySet ? 'Yes' : 'No'}
            </Badge>
          </div>
        </div>
        
        <!-- Help Text -->
        {#if authStatus.willUseSubscription}
          <div class="rounded-md bg-green-500/10 p-3">
            <p class="text-sm text-green-700 dark:text-green-400">
              🎉 Using your Claude subscription - no API costs!
            </p>
          </div>
        {:else if authStatus.apiKeySet}
          <div class="rounded-md bg-blue-500/10 p-3">
            <p class="text-sm text-blue-700 dark:text-blue-400">
              Using API key - pay-per-token billing applies
            </p>
          </div>
        {:else if authStatus.cliInstalled && !authStatus.cliAuthenticated}
          <div class="rounded-md bg-yellow-500/10 p-3">
            <p class="text-sm text-yellow-700 dark:text-yellow-400">
              ⚠️ Claude CLI installed but not authenticated
            </p>
            <p class="text-xs text-muted-foreground mt-1">
              Run: <code class="bg-muted px-1 rounded">claude</code> to authenticate
            </p>
          </div>
        {:else}
          <div class="rounded-md bg-destructive/10 p-3">
            <p class="text-sm text-destructive">
              ❌ No authentication configured
            </p>
            <p class="text-xs text-muted-foreground mt-1">
              Install Claude CLI or set ANTHROPIC_API_KEY
            </p>
          </div>
        {/if}
        
        <!-- Refresh Button -->
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