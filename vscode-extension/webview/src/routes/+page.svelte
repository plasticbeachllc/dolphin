
<script lang="ts">
  import { MessageList, ChatInput } from '$lib/components/chat';
  
  let messages = $state([
    {
      role: "assistant",
      content: `<p>Hi! I'm <strong>Dolphin</strong>, your AI coding assistant. 🐬</p><p>I can help you with:</p><ul class="list-disc list-inside mt-2"><li>Searching your codebase for relevant code</li><li>Reading and analyzing files</li><li>Writing new code or modifying existing files</li><li>Running commands and reviewing output</li></ul><p class="mt-3">Try asking me to:</p><ul class="list-disc list-inside mt-2"><li>"Search for authentication code"</li><li>"Read the main configuration file"</li><li>"Help me refactor this component"</li></ul>`,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }
  ]);
  
  let isProcessing = $state(false);
  
  async function handleSend(message: string) {
    if (isProcessing) return;
    
    // Add user message
    messages = [...messages, {
      role: "user",
      content: message,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }];
    
    isProcessing = true;
    
    // Simulate realistic agent workflow
    await new Promise(resolve => setTimeout(resolve, 300));
    
    // Assistant acknowledges
    messages = [...messages, {
      role: "assistant",
      content: `<p>Let me help you with that. I'll search the codebase first...</p>`,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }];
    
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Show tool call
    const toolCallIndex = messages.length;
    messages = [...messages, {
      type: "tool_call",
      tool: "search_knowledge",
      input: { query: message, top_k: 5 },
      status: "running"
    }];
    
    // Complete tool call after delay
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    messages = messages.map((msg, idx) =>
      idx === toolCallIndex
        ? {
            ...msg,
            status: "success",
            result: {
              hits: 3,
              files: ["src/components/App.svelte", "src/lib/utils.ts", "src/routes/+page.svelte"]
            },
            executionTime: 247
          }
        : msg
    );
    
    await new Promise(resolve => setTimeout(resolve, 300));
    
    // Final response
    messages = [...messages, {
      role: "assistant",
      content: `<p>I found <strong>3 relevant files</strong> in your codebase related to "${message}".</p><p class="mt-2">The most relevant files are:</p><ul class="list-disc list-inside mt-2"><li><code>src/components/App.svelte</code></li><li><code>src/lib/utils.ts</code></li><li><code>src/routes/+page.svelte</code></li></ul><p class="mt-3">Would you like me to read any of these files or help with something specific?</p>`,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }];
    
    isProcessing = false;
  }
</script>

<div class="chat-page">
  <div class="messages-container">
    <MessageList {messages} />
  </div>
  
  <div class="input-container">
    <ChatInput onSend={handleSend} disabled={isProcessing} />
  </div>
</div>

<style>
  .chat-page {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 3.5rem); /* Subtract navigation height (h-14 = 3.5rem) */
    background: var(--vscode-background);
  }
  
  .messages-container {
    flex: 1;
    overflow: hidden;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  
  .input-container {
    padding: 0.5rem;
    border-top: 1px solid var(--vscode-border);
    background: var(--vscode-background);
  }
</style>
