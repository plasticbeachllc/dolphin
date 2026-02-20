<script lang=\"ts\">
  import GalleryShowcase from '$lib/components/GalleryShowcase.svelte';
  import WelcomeCard from '$lib/components/WelcomeCard.svelte';

  let activeTab = $state('welcome');

  const tabs = [
    { id: 'welcome', label: 'Welcome Card' },
    // Add more tabs here as needed
  ];
</script>

<div class="gallery-container">
  <div class="gallery-header">
    <h1 class="gallery-title">🐬 Dolphin UI Gallery</h1>
    <p class="gallery-subtitle">Component previews and mockups for iteration</p>
  </div>

  <div class="tabs">
    {#each tabs as tab}
      <button
        class="tab"
        class:active={activeTab === tab.id}
        onclick={() => activeTab = tab.id}
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <div class="gallery-content">
    {#if activeTab === 'welcome'}
      <GalleryShowcase
        title="Welcome Card - First Time Setup"
        description="Appears when ~/.dolphin/config.toml doesn't exist. Shows a centered welcome card with initialization button."
      >
        {#snippet children()}
          <div class="preview-container">
            <!-- Mock the chat page background -->
            <div class="mock-chat-page">
              <WelcomeCard />
            </div>
          </div>

          <div class="preview-notes">
            <h3>Design Notes:</h3>
            <ul>
              <li><strong>Positioning:</strong> Centered, replaces the dolphin logo (🐬) when config is missing</li>
              <li><strong>Behavior:</strong> Auto-dismisses after successful initialization</li>
              <li><strong>User Flow:</strong> Click "Initialize Settings" → runs <code>uv run dolphin init</code> → creates ~/.dolphin/config.toml</li>
              <li><strong>States:</strong> Default, Loading, Error, Success (auto-hide)</li>
            </ul>

            <h3>Component Features:</h3>
            <ul>
              <li>VSCode theme-aware (uses CSS variables)</li>
              <li>Fade in/out transitions</li>
              <li>Loading spinner during initialization</li>
              <li>Error handling with helpful messages</li>
              <li>Hint text showing config path</li>
            </ul>
          </div>
        {/snippet}
      </GalleryShowcase>
    {/if}
  </div>
</div>

<style>
  .gallery-container {
    min-height: 100vh;
    padding: 2rem;
    background: var(--vscode-editor-background, #1e1e1e);
    color: var(--vscode-editor-foreground, #d4d4d4);
  }

  .gallery-header {
    margin-bottom: 2rem;
    text-align: center;
  }

  .gallery-title {
    font-size: 2rem;
    font-weight: 600;
    margin: 0 0 0.5rem 0;
    color: var(--vscode-foreground);
  }

  .gallery-subtitle {
    font-size: 1rem;
    color: var(--vscode-descriptionForeground);
    margin: 0;
  }

  .tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 2rem;
    border-bottom: 1px solid var(--vscode-panel-border);
    padding-bottom: 0;
  }

  .tab {
    padding: 0.75rem 1.5rem;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--vscode-descriptionForeground);
    cursor: pointer;
    font-size: 0.9375rem;
    font-weight: 500;
    transition: all 0.2s ease;
  }

  .tab:hover {
    color: var(--vscode-foreground);
    background: var(--vscode-list-hoverBackground);
  }

  .tab.active {
    color: var(--vscode-foreground);
    border-bottom-color: var(--vscode-focusBorder);
  }

  .gallery-content {
    max-width: 1200px;
    margin: 0 auto;
  }

  .preview-container {
    margin-bottom: 2rem;
  }

  .mock-chat-page {
    position: relative;
    min-height: 500px;
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 4px;
    overflow: hidden;
  }

  .preview-notes {
    margin-top: 2rem;
    padding: 1.5rem;
    background: var(--vscode-textBlockQuote-background);
    border-left: 3px solid var(--vscode-focusBorder);
    border-radius: 4px;
  }

  .preview-notes h3 {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.75rem 0;
    color: var(--vscode-foreground);
  }

  .preview-notes h3:not(:first-child) {
    margin-top: 1.5rem;
  }

  .preview-notes ul {
    margin: 0;
    padding-left: 1.5rem;
  }

  .preview-notes li {
    margin-bottom: 0.5rem;
    line-height: 1.6;
    color: var(--vscode-foreground);
  }

  .preview-notes code {
    background: var(--vscode-textCodeBlock-background);
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-family: var(--vscode-editor-font-family);
    font-size: 0.875rem;
  }

  .preview-notes strong {
    color: var(--vscode-foreground);
    font-weight: 600;
  }
</style>