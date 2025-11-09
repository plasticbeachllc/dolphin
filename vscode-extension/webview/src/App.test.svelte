<script lang="ts">
  let count = $state(0);
  
  function increment() {
    count++;
  }
</script>

<div class="test-container">
  <h1>Dolphin Test</h1>
  <p>If you see this, Svelte 5 is working!</p>
  <button onclick={increment}>
    Count: {count}
  </button>
</div>

<style>
  .test-container {
    padding: 2rem;
    background: var(--vscode-editor-background, #1e1e1e);
    color: var(--vscode-editor-foreground, #d4d4d4);
    height: 100vh;
  }
  
  h1 {
    color: var(--vscode-textLink-foreground, #4fc3f7);
  }
  
  button {
    padding: 0.5rem 1rem;
    background: var(--vscode-button-background, #0e639c);
    color: var(--vscode-button-foreground, white);
    border: none;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 1rem;
  }
  
  button:hover {
    background: var(--vscode-button-hoverBackground, #1177bb);
  }
</style>