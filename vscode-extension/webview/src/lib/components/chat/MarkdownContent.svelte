<script lang="ts">
  import { marked } from "marked";
  import CodeBlock from "./CodeBlock.svelte";
  
  interface Props {
    content: string;
  }
  
  let { content }: Props = $props();
  
  // Track code blocks to render separately
  let codeBlocks: Array<{ language: string; code: string; id: string }> = $state([]);
  let processedHtml = $state("");
  
  // Process markdown content
  $effect(() => {
    if (content) {
      codeBlocks = [];
      
      // Just use marked.parse with default settings (no custom renderer!)
      const parsed = marked.parse(content, {
        gfm: true,
        breaks: true
      }) as string;
      
      // Extract code blocks from the generated HTML
      const codeBlockRegex = /<pre><code class="language-(\w+)">([\s\S]*?)<\/code><\/pre>/g;
      let match;
      let processedContent = parsed;
      
      while ((match = codeBlockRegex.exec(parsed)) !== null) {
        const [fullMatch, language, code] = match;
        const id = `code-block-${Math.random().toString(36).substr(2, 9)}`;
        
        // Decode HTML entities in code
        const decodedCode = code
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&amp;/g, '&')
          .replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'");
        
        codeBlocks.push({
          id,
          language: language || "text",
          code: decodedCode,
        });
        
        processedContent = processedContent.replace(
          fullMatch,
          `<div data-code-block="${id}"></div>`
        );
      }
      
      processedHtml = processedContent;
    }
  });
</script>

<div class="markdown-content">
  {#each processedHtml.split(/(<div data-code-block="[^"]+"><\/div>)/) as segment}
    {#if segment.match(/^<div data-code-block="([^"]+)"><\/div>$/)}
      {@const match = segment.match(/data-code-block="([^"]+)"/)}
      {@const blockId = match?.[1]}
      {@const block = codeBlocks.find(b => b.id === blockId)}
      {#if block}
        <CodeBlock code={block.code} language={block.language} />
      {/if}
    {:else if segment}
      {@html segment}
    {/if}
  {/each}
</div>

<style>
  .markdown-content {
    font-family: var(--vscode-font-family), system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: var(--vscode-font-size, 13px);
    color: var(--vscode-editor-foreground, #d4d4d4);
    line-height: 1.6;
  }
  
  .markdown-content :global(p) {
    margin: 0.5em 0;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  
  .markdown-content :global(code:not(pre > code)) {
    font-family: var(--vscode-editor-font-family, monospace);
    font-size: 0.9em;
    background-color: var(--vscode-textCodeBlock-background, rgba(110, 118, 129, 0.2));
    color: var(--vscode-textPreformat-foreground, #e06c75);
    padding: 2px 4px;
    border-radius: 3px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  
  .markdown-content :global(a) {
    color: var(--vscode-textLink-foreground, #3794ff);
    text-decoration: none;
  }
  
  .markdown-content :global(a:hover) {
    color: var(--vscode-textLink-activeForeground, #4daafc);
    text-decoration: underline;
  }
  
  .markdown-content :global(h1) {
    font-size: 1.8em;
    font-weight: 600;
    margin: 1em 0 0.5em;
    border-bottom: 1px solid var(--vscode-panel-border, #2d2d30);
    padding-bottom: 0.3em;
  }
  
  .markdown-content :global(h2) {
    font-size: 1.5em;
    font-weight: 600;
    margin: 1em 0 0.5em;
  }
  
  .markdown-content :global(h3) {
    font-size: 1.25em;
    font-weight: 600;
    margin: 1em 0 0.5em;
  }
  
  .markdown-content :global(h4),
  .markdown-content :global(h5),
  .markdown-content :global(h6) {
    font-size: 1.1em;
    font-weight: 600;
    margin: 1em 0 0.5em;
  }
  
  .markdown-content :global(ul),
  .markdown-content :global(ol) {
    padding-left: 2em;
    margin: 0.5em 0;
  }
  
  .markdown-content :global(li) {
    margin: 0.25em 0;
  }
  
  .markdown-content :global(ul) {
    list-style-type: disc;
  }
  
  .markdown-content :global(ol) {
    list-style-type: decimal;
  }
  
  .markdown-content :global(blockquote) {
    border-left: 4px solid var(--vscode-textBlockQuote-border, #007acc);
    background-color: var(--vscode-textBlockQuote-background, rgba(0, 122, 204, 0.1));
    padding: 0.5em 1em;
    margin: 1em 0;
    font-style: italic;
  }
  
  .markdown-content :global(table) {
    border-collapse: collapse;
    margin: 1em 0;
    width: 100%;
  }
  
  .markdown-content :global(th),
  .markdown-content :global(td) {
    border: 1px solid var(--vscode-panel-border, #2d2d30);
    padding: 8px 12px;
    text-align: left;
  }
  
  .markdown-content :global(th) {
    background-color: var(--vscode-editor-background, #1e1e1e);
    font-weight: 600;
  }
  
  .markdown-content :global(tr:nth-child(even)) {
    background-color: var(--vscode-editor-inactiveSelectionBackground, rgba(110, 118, 129, 0.1));
  }
  
  .markdown-content :global(img) {
    max-width: 100%;
    height: auto;
    margin: 1em 0;
    border-radius: 4px;
  }
  
  .markdown-content :global(hr) {
    border: none;
    border-top: 1px solid var(--vscode-panel-border, #2d2d30);
    margin: 1.5em 0;
  }
  
  .markdown-content :global(strong) {
    font-weight: 600;
  }
  
  .markdown-content :global(em) {
    font-style: italic;
  }
  
  .markdown-content :global(del) {
    text-decoration: line-through;
    opacity: 0.7;
  }
</style>