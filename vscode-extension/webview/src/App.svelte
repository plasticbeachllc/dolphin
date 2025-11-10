<script lang="ts">
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { MessageList, ChatInput, ChatHeader } from '$lib/components/chat';
  import AppNavigation from '$lib/components/navigation/AppNavigation.svelte';
  import { sendMessage, onMessage, abortGeneration, saveState, getState } from '$lib/api/vscode';
  import type { AgentEvent } from '../../../shared/types/events';
  import SettingsPage from './routes/settings/+page.svelte';
  import ProfilePage from './routes/profile/+page.svelte';
  import ConversationsGallery from './routes/gallery/conversations/+page.svelte';
  
  // Message type matching MessageList expectations
  interface Message {
    type?: "tool_call" | "thinking";
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
    diff?: FileDiff;
  }
  
  interface FileDiff {
    oldFileName: string;
    newFileName: string;
    additions: number;
    deletions: number;
    hunks: DiffHunk[];
  }
  
  interface DiffHunk {
    oldStart: number;
    oldLines: number;
    newStart: number;
    newLines: number;
    lines: string[];
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

  // Accessibility: status announcements for screen readers
  let statusAnnouncement = $state<string>('');

  function announceStatus(message: string) {
    statusAnnouncement = message;
    // Clear after announcement to allow re-announcing the same message
    setTimeout(() => statusAnnouncement = '', 1000);
  }

  let messages = $state<Message[]>([]);

  let isProcessing = $state(false);
  
  // Computed messages with thinking indicator
  let displayMessages = $derived(
    isProcessing && !messages.some(m => m.type === 'thinking')
      ? [...messages, { type: 'thinking' as const, role: 'assistant' as const }]
      : messages.filter(m => m.type !== 'thinking')
  );

  // Track when persisted state has been restored to avoid overwriting it
  let hasRestoredState = $state(false);

  // Agent configuration
  let agentVersion = $state<string | undefined>(undefined);
  let model = $state<string>('claude-sonnet-4');
  let temperature = $state<number>(0.7);
  let toolsEnabled = $state<boolean>(true);
  
  // Workspace status - conversations require a workspace
  let hasWorkspace = $state(false);

  // Reference to ChatInput component to programmatically focus it
  let chatInputRef: any = null;

  // Set up message listener from VS Code extension
  onMount(() => {
    // Don't restore state - users should load conversations from gallery
    console.log('[App] Starting with blank slate - no auto-restore');
    hasRestoredState = true;

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
          console.log('[App] Agent ready event data:', event);
          agentReady = true;
          agentVersion = event.version;
          const eventHasWorkspace = (event as any).hasWorkspace;
          console.log('[App] Received hasWorkspace value:', eventHasWorkspace);
          hasWorkspace = eventHasWorkspace ?? true; // Default to true to be safe
          console.log('[App] Final workspace status:', hasWorkspace ? 'Open' : 'None');
          announceStatus('Dolphin agent is ready');
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
                toolId: msg.toolId,
                diff: event.diff
              };
              return updatedMsg;
            }
            return msg;
          });
          break;
          
        case 'task_completed':
          isProcessing = false;
          console.log('[App] Task completed:', event.success);
          announceStatus(event.success ? 'Task completed successfully' : 'Task completed with errors');
          break;

        case 'error':
          isProcessing = false;
          messages = [...messages, {
            role: 'assistant' as const,
            content: `**Error:** ${event.error.message}`,
            timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
          }];
          announceStatus(`Error: ${event.error.message}`);
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
          // Clear persisted state
          saveState({ messages: [], hasUserSentMessage: false });
          break;

        case 'prefill_input':
          // Prefill the chat input with text
          console.log('[App] Received prefill_input event with text:', event.text);
          chatInputRef?.prefill(event.text);
          break;

        case 'conversation_loaded':
          // When a conversation is loaded, restore messages and navigate to chat
          console.log('[App] Conversation loaded:', event.conversation);
          if (event.conversation && event.conversation.messages) {
            // Convert conversation messages to UI message format
            messages = event.conversation.messages.map((msg: any) => ({
              role: msg.role,
              content: msg.content,
              timestamp: new Date(msg.timestamp || Date.now()).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
            }));
            hasUserSentMessage = messages.length > 0;
            showLogo = false;
          }
          // Navigate to chat view
          currentView = '/';
          // Show branch info if present
          if (event.branchInfo) {
            console.log('[App] Loaded branch from:', event.branchInfo.originalTitle);
          }
          break;
        
        case 'workspace_changed':
          // Handle workspace changes (open/close folder)
          const newWorkspaceStatus = (event as any).hasWorkspace;
          console.log('[App] Workspace changed event:', event);
          console.log('[App] New workspace status:', newWorkspaceStatus ? 'Open' : 'Closed');
          console.log('[App] Current workspace status before change:', hasWorkspace ? 'Open' : 'Closed');
          
          // Only update if the status actually changed
          if (newWorkspaceStatus !== undefined && newWorkspaceStatus !== hasWorkspace) {
            hasWorkspace = newWorkspaceStatus;
            console.log('[App] Workspace status updated to:', hasWorkspace ? 'Open' : 'Closed');
            
            // If workspace was closed and user is on gallery, navigate to home
            if (!hasWorkspace && currentView === '/gallery/conversations') {
              console.log('[App] Workspace closed, navigating away from gallery');
              currentView = '/';
            }
          } else {
            console.log('[App] Workspace status unchanged, ignoring event');
          }
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
  <!-- Screen reader announcements -->
  <div class="sr-only" role="status" aria-live="polite" aria-atomic="true">
    {statusAnnouncement}
  </div>

  <!-- Loading banner shown until agent is ready -->
  {#if !agentReady}
    <div class="loading-banner" role="alert" aria-live="assertive">
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

  <AppNavigation currentPath={currentView} onNavigate={handleNavigate} {hasWorkspace} />
  
  {#if currentView === '/'}
    <main class="chat-page" aria-label="Chat interface">
      {#if agentReady}
        <ChatHeader
          {model}
          {temperature}
          {toolsEnabled}
          {agentVersion}
        />
      {/if}

      {#if showLogo && messages.length === 0 && agentReady}
        <div class="logo-container" transition:fade={{ duration: 600 }} aria-hidden="true">
          <div class="dolphin-logo">🐬</div>
        </div>
      {/if}

      <div class="messages-container" role="region" aria-label="Conversation messages">
        <MessageList messages={displayMessages} />
      </div>

      <div class="input-container">
        <ChatInput
          bind:this={chatInputRef}
          onSend={handleSend}
          onStop={handleStop}
          disabled={!agentReady}
          isProcessing={isProcessing}
          hasActiveConversation={hasUserSentMessage}
        />
      </div>
    </main>
  {:else if currentView === '/settings'}
    <main aria-label="Settings">
      <SettingsPage />
    </main>
  {:else if currentView === '/profile'}
    <main aria-label="Profile">
      <ProfilePage />
    </main>
  {:else if currentView === '/gallery/conversations'}
    <main aria-label="Conversation history">
      <ConversationsGallery onNavigate={handleNavigate} />
    </main>
  {:else if currentView === '/functions/architect'}
    <main class="placeholder-view" aria-label="Architect mode">
      <h2>Architect Mode</h2>
      <p>Generate architectural plans and design specifications</p>
    </main>
  {:else if currentView === '/functions/code-review'}
    <main class="placeholder-view" aria-label="Code review">
      <h2>Code Review</h2>
      <p>AI-powered code review with goal-oriented analysis</p>
    </main>
  {:else}
    <main class="placeholder-view" role="alert" aria-label="Page not found">
      <h2>404 - View not found</h2>
      <p>Path: {currentView}</p>
    </main>
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

  /* Screen reader only utility class */
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
  }
</style>