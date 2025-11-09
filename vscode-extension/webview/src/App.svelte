<script lang="ts">
  import { onMount } from 'svelte';
  import { MessageList, ChatInput } from '$lib/components/chat';
  import { sendMessage, onMessage } from '$lib/api/vscode';
  import type { AgentEvent } from '../../../shared/types/events';
  
  let messages = $state([
    {
      role: "assistant",
      content: `<p>Hi! I'm <strong>Dolphin</strong>, your AI coding assistant. 🐬</p><p>I can help you with:</p><ul class="list-disc list-inside mt-2"><li>Searching your codebase for relevant code</li><li>Reading and analyzing files</li><li>Writing new code or modifying existing files</li><li>Running commands and reviewing output</li></ul><p class="mt-3">Try asking me to:</p><ul class="list-disc list-inside mt-2"><li>"Search for authentication code"</li><li>"Read the main configuration file"</li><li>"Help me refactor this component"</li></ul>`,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }
  ]);
  
  let isProcessing = $state(false);
  
  // Set up message listener from VS Code extension
  onMount(() => {
    const unsubscribe = onMessage((event: AgentEvent) => {
      console.log('[App] Received event from extension:', event);
      
      switch (event.type) {
        case 'agent_ready':
          console.log('[App] Agent ready:', event.version);
          break;
          
        case 'content_delta':
          // Append content to last assistant message or create new one
          const lastMsg = messages[messages.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            messages = [...messages.slice(0, -1), {
              ...lastMsg,
              content: lastMsg.content + event.delta
            }];
          } else {
            messages = [...messages, {
              role: 'assistant',
              content: event.delta,
              timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
            }];
          }
          break;
          
        case 'tool_call_started':
          messages = [...messages, {
            type: 'tool_call',
            tool: event.tool,
            input: event.input,
            status: 'running',
            toolId: event.toolId
          }];
          break;
          
        case 'tool_call_completed':
          // Find and update the tool call message
          messages = messages.map(msg =>
            msg.toolId === event.toolId
              ? {
                  ...msg,
                  status: event.error ? 'error' : 'success',
                  result: event.result,
                  error: event.error,
                  executionTime: event.executionTime
                }
              : msg
          );
          break;
          
        case 'task_completed':
          isProcessing = false;
          console.log('[App] Task completed:', event.success);
          break;
          
        case 'error':
          isProcessing = false;
          messages = [...messages, {
            role: 'assistant',
            content: `<p class="text-destructive"><strong>Error:</strong> ${event.error.message}</p>`,
            timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
          }];
          break;
      }
    });
    
    return unsubscribe;
  });
  
  async function handleSend(message: string) {
    if (isProcessing) return;
    
    // Add user message
    messages = [...messages, {
      role: "user",
      content: message,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }];
    
    isProcessing = true;
    
    // Send to VS Code extension
    sendMessage(message);
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
    height: 100vh;
    background: var(--vscode-background);
  }
  
  .messages-container {
    flex: 1;
    overflow: hidden;
    min-height: 0;
  }
  
  .input-container {
    padding: 0.5rem;
    border-top: 1px solid var(--vscode-border);
    background: var(--vscode-background);
  }
</style>