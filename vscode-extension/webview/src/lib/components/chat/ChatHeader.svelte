<script lang="ts">
  import { Badge } from "$lib/components/ui/badge";

  interface Props {
    model?: string;
    temperature?: number;
    toolsEnabled?: boolean;
    agentVersion?: string;
  }

  let {
    model = "claude-sonnet-4",
    temperature = 0.7,
    toolsEnabled = true,
    agentVersion
  }: Props = $props();
</script>

<div class="chat-header" role="banner" aria-label="Chat configuration">
  <div class="header-badges">
    <Badge variant="secondary" aria-label="Model: {model}">
      <span class="badge-icon">🤖</span>
      {model}
    </Badge>

    <Badge variant="secondary" aria-label="Temperature: {temperature}">
      <span class="badge-icon">🌡️</span>
      temp: {temperature}
    </Badge>

    <Badge
      variant={toolsEnabled ? "default" : "outline"}
      aria-label="Tools {toolsEnabled ? 'enabled' : 'disabled'}"
    >
      <span class="badge-icon">🔧</span>
      {toolsEnabled ? 'Tools On' : 'Tools Off'}
    </Badge>

    {#if agentVersion}
      <Badge variant="outline" aria-label="Agent version {agentVersion}">
        v{agentVersion}
      </Badge>
    {/if}
  </div>
</div>

<style>
  .chat-header {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--vscode-panel-border, hsl(var(--border)));
    background: var(--vscode-sideBar-background, hsl(var(--background)));
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .header-badges {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
  }

  .badge-icon {
    margin-right: 0.25rem;
    font-size: 0.875em;
  }
</style>
