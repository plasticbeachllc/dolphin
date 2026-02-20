<script lang="ts">
  import { fade } from 'svelte/transition';
  import { getVSCodeAPI } from '$lib/api/vscode';

  let initializing = $state(false);
  let error = $state<string | null>(null);

  async function handleInitialize() {
    try {
      initializing = true;
      error = null;

      const vscode = getVSCodeAPI();
      vscode.postMessage({
        type: 'dolphin_init'
      });

      // Listen for response
      const handleMessage = (event: MessageEvent) => {
        const message = event.data;
        if (message.type === 'dolphin_init_response') {
          window.removeEventListener('message', handleMessage);

          if (message.error) {
            error = message.error;
            initializing = false;
          } else {
            // Success - config created, this component will be hidden
            initializing = false;
          }
        }
      };

      window.addEventListener('message', handleMessage);

      // Timeout after 10 seconds
      setTimeout(() => {
        if (initializing) {
          window.removeEventListener('message', handleMessage);
          error = 'Initialization timed out. Please try again.';
          initializing = false;
        }
      }, 10000);
    } catch (err: any) {
      error = err.message || 'Failed to initialize settings';
      initializing = false;
    }
  }
</script>

<div class="welcome-container" transition:fade={{ duration: 400 }}>
  <div class="welcome-card">
    <div class="welcome-icon">🐬</div>

    <h2 class="welcome-title">Welcome to Dolphin</h2>

    <p class="welcome-message">
      First time here? Initialize your settings to get started with semantic code search and AI-powered development.
    </p>

    {#if error}
      <div class="error-message" transition:fade={{ duration: 200 }}>
        <span class="error-icon">⚠️</span>
        <span>{error}</span>
      </div>
    {/if}

    <button
      class="initialize-button"
      onclick={handleInitialize}
      disabled={initializing}
    >
      {#if initializing}
        <span class="spinner"></span>
        <span>Initializing...</span>
      {:else}
        <span>Initialize Settings</span>
      {/if}
    </button>

    <p class="welcome-hint">
      This creates <code>~/.dolphin/config.toml</code> with default settings
    </p>
  </div>
</div>

<style>
  .welcome-container {
    position: absolute;
    top: 35%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 1;
    width: 90%;
    max-width: 420px;
  }

  .welcome-card {
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 8px;
    padding: 2rem;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .welcome-icon {
    font-size: 4rem;
    margin-bottom: 1rem;
    opacity: 0.9;
    filter: grayscale(0.2);
    user-select: none;
  }

  .welcome-title {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0 0 0.75rem 0;
    color: var(--vscode-foreground);
  }

  .welcome-message {
    font-size: 0.9375rem;
    line-height: 1.5;
    color: var(--vscode-descriptionForeground);
    margin: 0 0 1.5rem 0;
  }

  .error-message {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    background: var(--vscode-inputValidation-errorBackground);
    border: 1px solid var(--vscode-inputValidation-errorBorder);
    border-radius: 4px;
    padding: 0.75rem;
    margin-bottom: 1rem;
    font-size: 0.875rem;
    color: var(--vscode-errorForeground);
  }

  .error-icon {
    flex-shrink: 0;
  }

  .initialize-button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem 1.5rem;
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    border-radius: 4px;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .initialize-button:hover:not(:disabled) {
    background: var(--vscode-button-hoverBackground);
  }

  .initialize-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .welcome-hint {
    margin: 1rem 0 0 0;
    font-size: 0.8125rem;
    color: var(--vscode-descriptionForeground);
    opacity: 0.7;
  }

  .welcome-hint code {
    background: var(--vscode-textCodeBlock-background);
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-family: var(--vscode-editor-font-family);
    font-size: 0.8125rem;
  }
</style>