<script lang="ts">
  import { onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { MessageList, ChatInput, ChatHeader, ModeSelector, ArchitectModeBanner } from '$lib/components/chat';
  import AppNavigation from '$lib/components/navigation/AppNavigation.svelte';
  import WelcomeCard from '$lib/components/WelcomeCard.svelte';
  import {
    sendMessage,
    onMessage,
    abortGeneration,
    saveState,
    getState,
    getVSCodeAPI,
  } from '$lib/api/vscode';
  import type { ExtensionToWebviewMessage } from '@extension-shared/messages';
  import SettingsPage from './routes/settings/+page.svelte';
  import ProfilePage from './routes/profile/+page.svelte';
  import ConversationsGallery from './routes/gallery/conversations/+page.svelte';
  import KBPage from './routes/kb/+page.svelte';
  import { kbActions } from '$lib/stores/kb-store';
  
  // Message type matching MessageList expectations
  type ToolCallMessage = {
    type: "tool_call";
    tool: string;
    input: Record<string, unknown>;
    result?: unknown;
    error?: unknown;
    status?: "running" | "success" | "error";
    executionTime?: number;
    toolId?: string;
    diff?: FileDiff;
  };

  type ThinkingMessage = { type: "thinking"; role: "assistant" };

  type ChatMessage = {
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
  };

  type Message = ToolCallMessage | ThinkingMessage | ChatMessage;
  
  const isThinkingMessage = (m: Message): m is ThinkingMessage =>
    "type" in m && m.type === "thinking";
  const isToolCallMessage = (m: Message): m is ToolCallMessage =>
    "type" in m && m.type === "tool_call";
  
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

  let messages = $state<Message[]>([]);

  let isProcessing = $state(false);
  
  // Computed messages with thinking indicator
  let displayMessages = $derived(
    isProcessing && !messages.some(isThinkingMessage)
      ? [...messages, { type: 'thinking' as const, role: 'assistant' as const }]
      : messages.filter(m => !isThinkingMessage(m))
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
  
  // Dolphin config initialization status
  let configExists = $state(true); // Assume exists until we check
  let checkingConfig = $state(true);

  // EP-11: Architect mode selection
  let selectedMode = $state<'code' | 'architect'>('code');

  // Reference to ChatInput component to programmatically focus it
  let chatInputRef = $state<any>(null);

  // Live region for screen reader announcements
  let liveRegionMessage = $state<string>('');

  // Helper to announce messages to screen readers
  function announceToScreenReader(message: string) {
    liveRegionMessage = message;
    // Clear after announcement to allow repeat announcements
    setTimeout(() => {
      liveRegionMessage = '';
    }, 100);
  }

  // Set up message listener from VS Code extension
  onMount(() => {
    // Don't restore state - users should load conversations from gallery
    console.log('[App] Starting with blank slate - no auto-restore');
    hasRestoredState = true;
    
    // Check if config exists
    checkConfigExists();

    // Start tracking startup time
    startupTimer = window.setInterval(() => {
      if (!agentReady) {
        agentStartupTime += 1;
      }
    }, 1000);
    
    const unsubscribe = onMessage((event: ExtensionToWebviewMessage) => {
      console.log('[App] Received event from extension:', event);
      
      switch (event.type) {
        case 'agent_ready':
          console.log('[App] Agent ready:', event.version);
          console.log('[App] Agent ready event data:', event);
          agentReady = true;
          agentVersion = event.version;
          const eventHasWorkspace = (event as any).hasWorkspace;
          const workspaceName = (event as any).workspaceName;
          const workspacePath = (event as any).workspacePath;
          console.log('[App] Received hasWorkspace value:', eventHasWorkspace);
          console.log('[App] Received workspaceName:', workspaceName);
          console.log('[App] Received workspacePath:', workspacePath);
          hasWorkspace = eventHasWorkspace ?? true; // Default to true to be safe
          console.log('[App] Final workspace status:', hasWorkspace ? 'Open' : 'None');

          // Store workspace path globally for KB operations
          if (workspacePath) {
            (window as any).workspacePath = workspacePath;
          }

          // Initialize KB store with workspace name if available
          if (workspaceName) {
            kbActions.initialize(workspaceName, {});
          }
          
          if (startupTimer !== null) {
            clearInterval(startupTimer);
            startupTimer = null;
          }
          break;
          
        case 'content_delta':
          // Append content to last assistant message or create new one
          const lastMsg = messages[messages.length - 1];
          if (lastMsg && 'role' in lastMsg && 'content' in lastMsg && lastMsg.role === 'assistant') {
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
            type: 'tool_call',
            tool: event.tool,
            input: event.input as Record<string, unknown>,
            status: 'running',
            toolId: event.toolId
          }];
          break;
          
        case 'tool_call_completed':
          // Find and update the tool call message
          messages = messages.map(msg => {
            if (isToolCallMessage(msg) && msg.toolId === event.toolId) {
              const newStatus: "success" | "error" = event.error ? 'error' : 'success';
              return {
                ...msg,
                result: event.result,
                error: event.error,
                status: newStatus,
                executionTime: event.executionTime,
                diff: event.diff
              };
            }
            return msg;
          });
          break;
          
        case 'task_completed':
          isProcessing = false;
          console.log('[App] Task completed:', event.success);
          announceToScreenReader('Task completed');
          break;
          
        case 'error':
          isProcessing = false;
          messages = [...messages, {
            role: 'assistant' as const,
            content: `**Error:** ${event.error.message}`,
            timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
          }];
          announceToScreenReader(`Error: ${event.error.message}`);
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
          const rawMessages = Array.isArray((event as any).conversation?.messages)
            ? (event as any).conversation.messages
            : [];
          messages = rawMessages.map((msg: any) => ({
            role: msg.role,
            content: msg.content,
            timestamp: new Date(msg.timestamp || Date.now()).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
          })) as Message[];
          hasUserSentMessage = messages.length > 0;
          showLogo = false;
          // Navigate to chat view
          currentView = '/';
          // Show branch info if present
          if (event.branchInfo) {
            console.log('[App] Loaded branch from:', event.branchInfo.originalTitle);
          }
          break;
        
        case 'workspace_changed': {
          // Handle workspace changes (open/close folder)
          const { hasWorkspace: workspaceOpen, workspaceName } = event;
          console.log('[App] Workspace changed event:', event);
          console.log('[App] New workspace status:', workspaceOpen ? 'Open' : 'Closed');
          console.log('[App] New workspace name:', workspaceName);
          console.log('[App] Current workspace status before change:', hasWorkspace ? 'Open' : 'Closed');
          
          // Only update if the status actually changed
          if (workspaceOpen !== undefined && workspaceOpen !== hasWorkspace) {
            hasWorkspace = workspaceOpen;
            console.log('[App] Workspace status updated to:', hasWorkspace ? 'Open' : 'Closed');
            
            // Update KB store with new workspace name
            if (workspaceName) {
              kbActions.initialize(workspaceName, {});
            } else {
              kbActions.reset();
            }
            
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
        
        case 'dolphin_config_status':
          // Response from config existence check
          console.log('[App] Config status received:', event);
          configExists = event.exists ?? true;
          checkingConfig = false;
          break;
        
        case 'dolphin_init_response':
          // Response from initialization
          console.log('[App] Init response received:', event);
          if (event.success && !event.error) {
            // Success - config now exists
            configExists = true;
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

    // Send to VS Code extension with selected mode
    sendMessage(message, selectedMode);
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
  
  function checkConfigExists() {
    try {
      const vscode = getVSCodeAPI();
      vscode.postMessage({ type: 'check_dolphin_config' });
    } catch (error) {
      console.warn('[App] Unable to check config status:', error);
      checkingConfig = false;
    }
  }
</script>

<div class="app-container">
  <!-- Loading banner shown until agent is ready -->
  {#if !agentReady}
    <div class="loading-banner" role="status" aria-live="polite" aria-atomic="true">
      <div class="loading-content">
        <div class="loading-spinner" aria-hidden="true"></div>
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
    <div class="chat-page">
      {#if agentReady}
        <ChatHeader
          {model}
          {temperature}
          {toolsEnabled}
          {agentVersion}
        />
      {/if}

      {#if showLogo && messages.length === 0 && agentReady}
        {#if !configExists && !checkingConfig}
          <WelcomeCard />
        {:else}
          <div class="logo-container" transition:fade={{ duration: 600 }}>
            <div class="dolphin-logo">🐬</div>
          </div>
        {/if}
      {/if}

      <div class="messages-container">
        <MessageList messages={displayMessages} />
      </div>

      <div class="input-container">
        {#if agentReady}
          <ModeSelector bind:value={selectedMode} />

          {#if selectedMode === 'architect'}
            <ArchitectModeBanner />
          {/if}
        {/if}

        <ChatInput
          bind:this={chatInputRef}
          onSend={handleSend}
          onStop={handleStop}
          disabled={!agentReady}
          isProcessing={isProcessing}
          hasActiveConversation={hasUserSentMessage}
        />
      </div>
    </div>
  {:else if currentView === '/settings'}
    <SettingsPage />
  {:else if currentView === '/profile'}
    <ProfilePage />
  {:else if currentView === '/gallery/conversations'}
    <ConversationsGallery onNavigate={handleNavigate} />
  {:else if currentView === '/kb'}
    <KBPage />
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

<!-- Live region for screen reader announcements - Accessibility Guide requirement -->
<div
  id="live-region"
  role="status"
  aria-live="polite"
  aria-atomic="true"
  class="sr-only"
>
  {liveRegionMessage}
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
