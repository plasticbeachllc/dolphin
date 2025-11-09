<script lang="ts">
  import { onMount } from 'svelte';
  import { MessageList, ChatInput } from '$lib/components/chat';
  import AppNavigation from '$lib/components/navigation/AppNavigation.svelte';
  import { sendMessage, onMessage } from '$lib/api/vscode';
  import type { AgentEvent } from '../../../shared/types/events';
  import SettingsPage from './routes/settings/+page.svelte';
  import ProfilePage from './routes/profile/+page.svelte';
  
  let currentView = $state('/');
  
  function handleNavigate(path: string) {
    currentView = path;
    console.log('[App] Navigating to:', path);
  }
  
  // Agent startup state
  let agentReady = $state(false);
  let agentStartupTime = $state(0);
  let startupTimer: number | null = null;
  
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
    // Start tracking startup time
    startupTimer = window.setInterval(() => {
      if (!agentReady) {
        agentStartupTime += 1;
      }
    }, 1000);
    
    const unsubscribe = onMessage((event: AgentEvent) => {
      console.log('[App] Received event from extension:', event);
      
      switch (event.type) {
        case 'agent_ready':
          console.log('[App] Agent ready:', event.version);
          agentReady = true;
          if (startupTimer !== null) {
            clearInterval(startupTimer);
            startupTimer = null;
          }
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
    
    return () => {
      unsubscribe();
      if (startupTimer !== null) {
        clearInterval(startupTimer);
      }
    };
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

<div class="app-container">
  <!-- Loading banner shown until agent is ready -->
  {#if !agentReady}
    <div class="loading-banner">
      <div class="loading-content">
        <div class="loading-spinner"></div>
        <div class="loading-text">
          <strong>Starting Dolphin Agent...</strong>
          <span class="loading-subtext">
            {#if agentStartupTime < 10}
              Initializing services
            {:else if agentStartupTime < 30}
              Starting knowledge base server ({agentStartupTime}s)
            {:else}
              This is taking longer than usual ({agentStartupTime}s)
            {/if}
          </span>
        </div>
      </div>
    </div>
  {/if}
  
  <AppNavigation currentPath={currentView} onNavigate={handleNavigate} />
  
  {#if currentView === '/'}
    <div class="chat-page">
      <div class="messages-container">
        <MessageList {messages} />
      </div>
      
      <div class="input-container">
        <ChatInput onSend={handleSend} disabled={isProcessing} />
      </div>
    </div>
  {:else if currentView === '/settings'}
    <SettingsPage />
  {:else if currentView === '/profile'}
    <ProfilePage />
  {:else if currentView === '/functions/architect'}
    <div class="placeholder-view">
      <h2>Architect Mode</h2>
      <p>Generate architectural plans and design specifications</p>
    </div>
  {:else if currentView === '/functions/code-review'}
    <div class="placeholder-view">
      <h2>Code Review</h2>
      <p>AI-powered code review with goal-oriented analysis</p>
    </div>
  {:else}
    <div class="placeholder-view">
      <h2>404 - View not found</h2>
      <p>Path: {currentView}</p>
    </div>
  {/if}
</div>

<style>
  .app-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: var(--vscode-background);
  }
  
  .loading-banner {
    background: var(--vscode-editorInfo-background);
    border-bottom: 1px solid var(--vscode-editorInfo-border);
    padding: 0.75rem 1rem;
    animation: slideDown 0.3s ease-out;
  }
  
  @keyframes slideDown {
    from {
      transform: translateY(-100%);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }
  
  .loading-content {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    max-width: 800px;
    margin: 0 auto;
  }
  
  .loading-spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--vscode-editorInfo-foreground);
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .loading-text {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    color: var(--vscode-editorInfo-foreground);
    font-size: 0.875rem;
  }
  
  .loading-subtext {
    font-size: 0.75rem;
    opacity: 0.8;
  }
  
  .chat-page {
    display: flex;
    flex-direction: column;
    flex: 1;
    overflow: hidden;
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
  
  .placeholder-view {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--vscode-foreground);
  }
  
  .placeholder-view h2 {
    font-size: 1.5rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  
  .placeholder-view p {
    color: var(--vscode-descriptionForeground);
  }
</style>