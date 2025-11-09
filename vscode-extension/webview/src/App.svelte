<script lang="ts">
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { MessageList, ChatInput } from '$lib/components/chat';
  import AppNavigation from '$lib/components/navigation/AppNavigation.svelte';
  import { sendMessage, onMessage, abortGeneration } from '$lib/api/vscode';
  import type { AgentEvent } from '../../../shared/types/events';
  import SettingsPage from './routes/settings/+page.svelte';
  import ProfilePage from './routes/profile/+page.svelte';
  
  // Message type matching MessageList expectations
  interface Message {
    type?: "tool_call";
    role?: "user" | "assistant";
    content?: string;
    timestamp?: string;
    tool?: string;
    input?: Record<string, any>;
    result?: Record<string, any>;
    error?: string;
    status?: "running" | "success" | "error";
    executionTime?: number;
    toolId?: string;
  }
  
  let currentView = $state('/');
  
  function handleNavigate(path: string) {
    currentView = path;
    console.log('[App] Navigating to:', path);
  }
  
  // Agent startup state
  let agentReady = $state(false);
  let agentStartupTime = $state(0);
  let startupTimer: number | null = null;
  let showLogo = $state(true);
  let hasUserSentMessage = $state(false);
  
  let messages = $state<Message[]>([]);

  let isProcessing = $state(false);

  // Reference to ChatInput component to programmatically focus it
  let chatInputRef: any = null;

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
              content: (lastMsg.content || '') + event.delta
            }];
          } else {
            messages = [...messages, {
              role: 'assistant' as const,
              content: event.delta,
              timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
            }];
          }
          break;
          
        case 'tool_call_started':
          messages = [...messages, {
            type: 'tool_call' as const,
            tool: event.tool,
            input: event.input,
            status: 'running' as const,
            toolId: event.toolId
          }];
          break;
          
        case 'tool_call_completed':
          // Find and update the tool call message
          messages = messages.map(msg => {
            if (msg.toolId === event.toolId) {
              const newStatus: "success" | "error" = event.error ? 'error' : 'success';
              const updatedMsg: Message = {
                type: msg.type,
                role: msg.role,
                content: msg.content,
                timestamp: msg.timestamp,
                tool: msg.tool,
                input: msg.input,
                result: event.result,
                error: event.error,
                status: newStatus,
                executionTime: event.executionTime,
                toolId: msg.toolId
              };
              return updatedMsg;
            }
            return msg;
          });
          break;
          
        case 'task_completed':
          isProcessing = false;
          console.log('[App] Task completed:', event.success);
          break;
          
        case 'error':
          isProcessing = false;
          messages = [...messages, {
            role: 'assistant' as const,
            content: `**Error:** ${event.error.message}`,
            timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
          }];
          break;

        case 'focus_input':
          // Focus the chat input
          console.log('[App] Received focus_input event');
          chatInputRef?.focus();
          break;

        case 'clear_conversation':
          // Clear all messages and reset state
          console.log('[App] Received clear_conversation event');
          messages = [];
          isProcessing = false;
          showLogo = true;
          hasUserSentMessage = false;
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
    
    // Hide logo on first message send
    if (!hasUserSentMessage) {
      hasUserSentMessage = true;
      showLogo = false;
    }
    
    // Add user message
    messages = [...messages, {
      role: "user" as const,
      content: message,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }];
    
    isProcessing = true;
    
    // Send to VS Code extension
    sendMessage(message);
  }
  
  function handleStop() {
    if (!isProcessing) return;
    
    // Send abort signal to extension
    abortGeneration();
    
    isProcessing = false;
    
    // Add system message
    messages = [...messages, {
      role: 'assistant' as const,
      content: '⏹️ **Generation stopped by user**',
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }];
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
      {#if showLogo && messages.length === 0 && agentReady}
        <div class="logo-container" transition:fade={{ duration: 600 }}>
          <div class="dolphin-logo">🐬</div>
        </div>
      {/if}
      
      <div class="messages-container">
        <MessageList {messages} />
      </div>
      
      <div class="input-container">
        <ChatInput
          bind:this={chatInputRef}
          onSend={handleSend}
          onStop={handleStop}
          disabled={!agentReady}
          isProcessing={isProcessing}
        />
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
    padding: 0.375rem 0.75rem;
    height: 2.5rem;
    display: flex;
    align-items: center;
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
    gap: 0.5rem;
  }
  
  .loading-spinner {
    width: 14px;
    height: 14px;
    border: 2px solid var(--vscode-editorInfo-foreground);
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .loading-text {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--vscode-editorInfo-foreground);
    font-size: 0.8125rem;
    white-space: nowrap;
  }
  
  .loading-subtext {
    font-size: 0.75rem;
    opacity: 0.8;
    font-weight: normal;
  }
  
  .chat-page {
    position: relative;
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
    padding: 0.75rem;
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
  
  .logo-container {
    position: absolute;
    top: 35%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 1;
  }
  
  .dolphin-logo {
    font-size: 6rem;
    text-align: center;
    opacity: 0.3;
    filter: grayscale(0.3);
    user-select: none;
  }
</style>