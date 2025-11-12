<script lang="ts">
  import hljs from "highlight.js";
  import { Copy, Check } from "lucide-svelte";
  
  interface Props {
    code: string;
    language?: string;
  }
  
  let { code, language = "text" }: Props = $props();
  
  let copied = $state(false);
  
  // Generate highlighted HTML without DOM mutation
  // This prevents the infinite loop caused by hljs.highlightElement()
  let highlightedCode = $derived.by(() => {
    try {
      const result = hljs.highlight(code, { language, ignoreIllegals: true });
      return result.value;
    } catch (err) {
      console.error("Failed to highlight code:", err);
      // Fallback to plain code with HTML escaping
      return code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }
  });
  
  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      copied = true;
      setTimeout(() => {
        copied = false;
      }, 2000);
    } catch (err) {
      console.error("Failed to copy code:", err);
    }
  }
</script>

<div class="code-block-container">
  <div class="code-header">
    <span class="language-label">{language}</span>
    <button
      class="copy-button"
      onclick={copyCode}
      aria-label="Copy code"
    >
      {#if copied}
        <Check size={16} />
      {:else}
        <Copy size={16} />
      {/if}
    </button>
  </div>
  <pre class="code-content"><code class="language-{language} hljs">{@html highlightedCode}</code></pre>
</div>

<style>
  .code-block-container {
    position: relative;
    margin: 1em 0;
    background-color: var(--vscode-editor-background, #1e1e1e);
    border-radius: 6px;
    overflow: hidden;
  }
  
  .code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 1rem;
    background-color: var(--vscode-editor-background, #1e1e1e);
    border-bottom: 1px solid var(--vscode-panel-border, #2d2d30);
  }
  
  .language-label {
    font-size: 0.75rem;
    color: var(--vscode-descriptionForeground, #999);
    text-transform: uppercase;
    font-family: var(--vscode-editor-font-family, monospace);
  }
  
  .copy-button {
    background: transparent;
    border: none;
    color: var(--vscode-foreground, #ccc);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 3px;
    opacity: 0.6;
    transition: opacity 0.2s, background-color 0.2s;
  }
  
  .copy-button:hover {
    opacity: 1;
    background-color: var(--vscode-toolbar-hoverBackground, #2a2d2e);
  }
  
  .code-content {
    margin: 0;
    padding: 1rem;
    overflow-x: auto;
    background-color: var(--vscode-editor-background, #1e1e1e);
  }
  
  .code-content code {
    font-family: var(--vscode-editor-font-family, "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace);
    font-size: 0.9em;
    line-height: 1.5;
    color: var(--vscode-editor-foreground, #d4d4d4);
    white-space: pre;
    word-break: normal;
    overflow-wrap: normal;
  }
  
  /* VSCode theme compatibility */
  :global(.hljs) {
    background: var(--vscode-editor-background, #1e1e1e) !important;
    color: var(--vscode-editor-foreground, #d4d4d4) !important;
  }
</style>