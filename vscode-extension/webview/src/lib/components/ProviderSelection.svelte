<script lang="ts">
  import { onMount } from 'svelte';
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { getVSCodeAPI } from '$lib/api/vscode';
  import { Check, AlertCircle, Zap } from 'lucide-svelte';
  import type { ProviderAuthStatus } from './auth-status-helpers';

  interface ProviderOption {
    id: string;
    label: string;
    description: string;
    models: ModelOption[];
  }

  interface ModelOption {
    id: string;
    label: string;
    description: string;
    default?: boolean;
  }

  interface ProviderSettingsPayload {
    currentProvider: string;
    currentModel: string;
    availableProviders: ProviderOption[];
  }

  let availableProviders = $state<ProviderOption[]>([]);
  let currentProvider = $state<string>('');
  let currentModel = $state<string>('');
  let providerStatuses = $state<ProviderAuthStatus[]>([]);
  let loading = $state(true);
  let saving = $state(false);

  onMount(async () => {
    await fetchProviderSettings();
    await fetchAuthStatus();
  });

  async function fetchProviderSettings() {
    try {
      const vscode = getVSCodeAPI();
      const handleMessage = (event: MessageEvent) => {
        const message = event.data as { type?: string } & Partial<ProviderSettingsPayload>;
        if (message.type === 'provider_settings') {
          availableProviders = message.availableProviders ?? [];
          currentProvider = message.currentProvider ?? '';
          currentModel = message.currentModel ?? '';
          loading = false;
          clearTimeout(timeout);
          window.removeEventListener('message', handleMessage);
        }
      };

      window.addEventListener('message', handleMessage);
      vscode.postMessage({ type: 'get_provider_settings' });

      const timeout = setTimeout(() => {
        if (loading) {
          loading = false;
          window.removeEventListener('message', handleMessage);
        }
      }, 5000);
    } catch (err) {
      loading = false;
    }
  }

  async function fetchAuthStatus() {
    try {
      const vscode = getVSCodeAPI();
      const handleMessage = (event: MessageEvent) => {
        const message = event.data as { type?: string; status?: { providers: ProviderAuthStatus[] } };
        if (message.type === 'auth_status') {
          providerStatuses = message.status?.providers ?? [];
          clearTimeout(timeout);
          window.removeEventListener('message', handleMessage);
        }
      };

      window.addEventListener('message', handleMessage);
      vscode.postMessage({ type: 'get_auth_status' });

      const timeout = setTimeout(() => {
        window.removeEventListener('message', handleMessage);
      }, 5000);
    } catch (err) {
      // Silently fail
    }
  }

  function getAuthStatus(providerId: string): ProviderAuthStatus | undefined {
    return providerStatuses.find(s => s.provider.toLowerCase() === providerId.toLowerCase());
  }

  function isAuthenticated(providerId: string): boolean {
    return getAuthStatus(providerId)?.authenticated ?? false;
  }

  async function selectProvider(providerId: string) {
    if (providerId === currentProvider) return;

    const provider = availableProviders.find(p => p.id === providerId);
    if (!provider) return;

    // Auto-select default model for this provider
    const defaultModel = provider.models.find(m => m.default);
    const modelId = defaultModel?.id ?? provider.models[0]?.id ?? '';

    saving = true;
    try {
      const vscode = getVSCodeAPI();
      vscode.postMessage({
        type: 'save_provider_settings',
        provider: providerId,
        model: modelId
      });

      // Update local state optimistically
      currentProvider = providerId;
      currentModel = modelId;

      // Wait for confirmation message
      const handleMessage = (event: MessageEvent) => {
        const message = event.data as { type?: string };
        if (message.type === 'provider_settings') {
          saving = false;
          clearTimeout(timeout);
          window.removeEventListener('message', handleMessage);
        }
      };

      window.addEventListener('message', handleMessage);

      const timeout = setTimeout(() => {
        saving = false;
        window.removeEventListener('message', handleMessage);
      }, 3000);
    } catch (err) {
      saving = false;
    }
  }

  async function setupProvider(providerId: string) {
    const vscode = getVSCodeAPI();
    vscode.postMessage({
      type: 'setSecret',
      provider: providerId
    });
  }
</script>

<Card>
  <CardHeader>
    <CardTitle class="flex items-center gap-2">
      <Zap class="h-5 w-5" />
      AI Provider Selection
    </CardTitle>
    <CardDescription>
      Choose your AI provider and authenticate to start using Dolphin
    </CardDescription>
  </CardHeader>
  <CardContent>
    {#if loading}
      <div class="flex items-center space-x-2">
        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
        <p class="text-sm text-muted-foreground">Loading providers...</p>
      </div>
    {:else}
      <div class="space-y-3">
        {#each availableProviders as provider}
          {@const authenticated = isAuthenticated(provider.id)}
          {@const selected = currentProvider === provider.id}
          
          <button
            onclick={() => selectProvider(provider.id)}
            disabled={saving}
            class="w-full text-left rounded-lg border-2 p-4 transition-all hover:bg-accent/50 disabled:opacity-50 disabled:cursor-not-allowed {selected ? 'border-primary bg-accent' : 'border-border'}"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1 space-y-1">
                <div class="flex items-center gap-2">
                  <p class="font-medium">{provider.label}</p>
                  {#if selected}
                    <Badge variant="default" class="text-xs">Active</Badge>
                  {/if}
                </div>
                <p class="text-sm text-muted-foreground">{provider.description}</p>
                {#if selected && currentModel}
                  <p class="text-xs text-muted-foreground">
                    Model: {provider.models.find(m => m.id === currentModel)?.label ?? currentModel}
                  </p>
                {/if}
              </div>
              
              <div class="flex flex-col items-end gap-2">
                {#if authenticated}
                  <div class="flex items-center gap-1 text-green-600 dark:text-green-400">
                    <Check class="h-4 w-4" />
                    <span class="text-xs font-medium">Authenticated</span>
                  </div>
                {:else}
                  <div class="flex items-center gap-1 text-orange-600 dark:text-orange-400">
                    <AlertCircle class="h-4 w-4" />
                    <span class="text-xs font-medium">Not Setup</span>
                  </div>
                {/if}
                
                {#if !authenticated}
                  <Button
                    size="sm"
                    variant="outline"
                    onclick={(e) => {
                      e.stopPropagation();
                      setupProvider(provider.id);
                    }}
                  >
                    Setup API Key
                  </Button>
                {/if}
              </div>
            </div>
          </button>
        {/each}

        {#if availableProviders.length === 0}
          <div class="rounded-md bg-secondary/30 p-4">
            <p class="text-sm text-muted-foreground">
              No providers available. Please check your extension configuration.
            </p>
          </div>
        {/if}
      </div>
    {/if}
  </CardContent>
</Card>
