# Phase 5: Conversation Persistence - Implementation Plan

**Version:** 1.0  
**Date:** 2025-11-09  
**Status:** Ready for Implementation  

---

## Executive Summary

This plan implements conversation persistence for the Dolphin VSCode extension based on Phase 5 requirements. The implementation uses a **hybrid architecture** combining file-based persistence (ConversationStore) with webview state caching for optimal performance and data durability.

---

## Architecture Decisions (Finalized)

### 1. Storage Architecture
**Decision:** Hybrid approach
- **Primary storage:** File-based ConversationStore (`.dolphin/state/conversations/`)
- **Cache layer:** Webview state (`vscode.setState()`)
- **Rationale:** Combines unlimited storage with fast restoration

### 2. UI Surface Location
**Decision:** Panel within webview
- **Location:** Conversations button in AppNavigation
- **View mode:** Timeline view (default)
- **Rationale:** Consistent with existing navigation pattern, rich UI capabilities

### 3. Auto-save Behavior
**Decision:** Auto-save on every message
- **Trigger:** After each user/assistant message is added
- **Mechanism:** Update both ConversationStore and webview state
- **Rationale:** No user intervention needed, matches user expectations

### 4. Conversation Forking
**Decision:** Create new branch
- **Behavior:** When loading old conversation and sending new message, create new conversation ID
- **Preservation:** Original conversation remains unchanged
- **Rationale:** Non-destructive, preserves conversation history

### 5. Conversation Titles
**Decision:** Auto-generate from first message
- **Strategy:** Use first 50 characters of first user message
- **Editable:** User can rename via UI
- **Rationale:** Low friction, immediate value

### 6. Metadata to Capture
**Decision:** File references and token tracking (MVP)
- **Included:** `files: string[]`, `token_count: number`, `pinned: boolean`
- **Deferred:** Git context, tags (Phase 5b)
- **Rationale:** Focus on high-value, low-complexity metadata

### 7. Default View Mode
**Decision:** Timeline view
- **Configurable:** Yes, user preference stored in webview state
- **Rationale:** User-preferred for temporal context

### 8. Export Format
**Decision:** JSON (MVP)
- **Format:** Complete conversation dump with all metadata
- **Deferred:** Markdown, PDF (Phase 5b)
- **Rationale:** Simple, full-fidelity, machine-readable

### 9. Cleanup Policy
**Decision:** Unlimited storage (MVP)
- **Future:** Add cleanup handler in Phase 5b
- **Rationale:** Simplify MVP, address when needed

---

## Extended Schema Design

### Current Schema (from `shared/types/state.ts`)
```typescript
ConversationSchema = {
  schema_version: "1.0",
  conversation: {
    id: string,
    created_at: string,
    updated_at: string,
    workspace_root: string
  },
  messages: ConversationMessage[],
  summaries?: array
}

ConversationMessage = {
  id: string,
  role: "user" | "assistant",
  content: string,
  timestamp: string,
  pinned?: boolean
}
```

### **NEW: Extended Schema for Phase 5**

```typescript
// shared/types/state.ts - UPDATED

export const ConversationMetadataSchema = z.object({
  // Core metadata
  title: z.string().default("Untitled Conversation"),
  
  // File tracking
  files: z.array(z.string()).default([]),
  
  // Token tracking
  token_count: z.number().default(0),
  
  // UI state
  pinned: z.boolean().default(false),
  
  // Parent conversation (for branching)
  parent_conversation_id: z.string().optional(),
  branch_point_message_id: z.string().optional(),
  
  // Last active timestamp
  last_active_at: z.string().optional(),
});

export const ConversationSchema = z.object({
  schema_version: z.string().default("1.0"),
  conversation: z.object({
    id: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
    workspace_root: z.string(),
  }),
  
  // NEW: Metadata section
  metadata: ConversationMetadataSchema.optional().default({}),
  
  messages: z.array(ConversationMessageSchema),
  summaries: z
    .array(
      z.object({
        range_start: z.number(),
        range_end: z.number(),
        key_points: z.array(z.string()),
        created_at: z.string(),
      })
    )
    .optional(),
});

export type ConversationMetadata = z.infer<typeof ConversationMetadataSchema>;
```

### **NEW: Webview State Schema**

```typescript
// vscode-extension/webview/src/lib/types/state.ts - NEW FILE

export interface WebviewPersistedState {
  // Current active conversation
  activeConversationId: string | null;
  
  // Current messages (for quick restore)
  messages: Message[];
  
  // UI state
  hasUserSentMessage: boolean;
  showLogo: boolean;
  
  // Preferences
  conversationViewMode: 'grid' | 'list' | 'timeline';
  
  // Last save timestamp
  lastSaved: number;
}
```

---

## Implementation Plan

### **Phase 5a: MVP (Priority 1) - 2 days**

#### **Task 1: Extend Conversation Schema** (1 hour)
**Files:**
- `shared/types/state.ts` - Add ConversationMetadataSchema

**Changes:**
```typescript
// Add metadata to ConversationSchema
metadata: ConversationMetadataSchema.optional().default({})
```

**Testing:**
- Unit test schema validation
- Ensure backward compatibility with existing conversations

---

#### **Task 2: Update ConversationStore** (2 hours)
**Files:**
- `agent-core/src/storage/conversation-store.ts`

**New methods:**
```typescript
// Update conversation metadata
async updateMetadata(
  conversationId: string, 
  metadata: Partial<ConversationMetadata>
): Promise<void>

// List conversations with metadata
async listConversationsWithMetadata(): Promise<Array<{
  id: string;
  metadata: ConversationMetadata;
  created_at: string;
  updated_at: string;
}>>

// Create new conversation from existing (for branching)
async branchConversation(
  parentId: string,
  branchPointMessageId: string,
  newMessages: ConversationMessage[]
): Promise<Conversation>
```

**Testing:**
- Unit tests for new methods
- Integration test for branching behavior

---

#### **Task 3: Add JSON-RPC Methods in Agent Core** (2 hours)
**Files:**
- `agent-core/src/main.ts`

**New RPC methods:**
```typescript
// List all conversations
rpc.handle('list_conversations', async () => {
  return await conversationStore.listConversationsWithMetadata();
});

// Load specific conversation
rpc.handle('load_conversation', async ({ conversationId }) => {
  return await conversationStore.loadConversation(conversationId);
});

// Delete conversation
rpc.handle('delete_conversation', async ({ conversationId }) => {
  await conversationStore.deleteConversation(conversationId);
});

// Update conversation metadata (e.g., title, pinned)
rpc.handle('update_conversation_metadata', async ({ conversationId, metadata }) => {
  await conversationStore.updateMetadata(conversationId, metadata);
});

// Export conversation to JSON
rpc.handle('export_conversation', async ({ conversationId }) => {
  const conv = await conversationStore.loadConversation(conversationId);
  return JSON.stringify(conv, null, 2);
});
```

**Testing:**
- E2E test for RPC methods via bridge

---

#### **Task 4: Auto-save Integration in App.svelte** (3 hours)
**Files:**
- `vscode-extension/webview/src/App.svelte`
- `vscode-extension/webview/src/lib/api/vscode.ts`

**Implementation:**

```typescript
// App.svelte - NEW state management

import { saveState, getState } from '$lib/api/vscode';

// Track current conversation ID
let activeConversationId = $state<string | null>(null);

// Auto-save effect
$effect(() => {
  if (messages.length > 0) {
    // Save to webview state (fast)
    saveState({
      activeConversationId,
      messages,
      hasUserSentMessage,
      showLogo,
      lastSaved: Date.now()
    });
    
    // Save to ConversationStore (durable)
    saveConversationToDisk();
  }
});

async function saveConversationToDisk() {
  if (!agentReady || messages.length === 0) return;
  
  // Generate conversation ID if new
  if (!activeConversationId) {
    activeConversationId = `conv_${Date.now()}`;
  }
  
  // Extract title from first user message
  const firstUserMsg = messages.find(m => m.role === 'user');
  const title = firstUserMsg?.content.slice(0, 50) || 'Untitled Conversation';
  
  // Track file references (extract from tool calls)
  const files = extractFileReferences(messages);
  
  // Send to extension to save via ConversationStore
  sendMessage({
    type: 'save_conversation',
    conversationId: activeConversationId,
    messages: messages.map(m => ({
      id: m.timestamp || `msg_${Date.now()}`,
      role: m.role || 'assistant',
      content: m.content || '',
      timestamp: new Date().toISOString(),
    })),
    metadata: {
      title,
      files,
      token_count: 0, // TODO: track from agent responses
      pinned: false,
      last_active_at: new Date().toISOString()
    }
  });
}

// Restore conversation on mount
onMount(() => {
  const savedState = getState();
  if (savedState) {
    activeConversationId = savedState.activeConversationId;
    messages = savedState.messages || [];
    hasUserSentMessage = savedState.hasUserSentMessage || false;
    showLogo = savedState.showLogo ?? true;
  }
});

// Helper to extract file references from messages
function extractFileReferences(messages: Message[]): string[] {
  const files = new Set<string>();
  messages.forEach(msg => {
    if (msg.type === 'tool_call') {
      // Extract file paths from tool inputs/results
      if (msg.input?.path) files.add(msg.input.path);
      if (msg.input?.paths) msg.input.paths.forEach((p: string) => files.add(p));
    }
  });
  return Array.from(files);
}
```

**New vscode.ts method:**
```typescript
// vscode-extension/webview/src/lib/api/vscode.ts

export function saveConversation(data: any) {
  const api = getVSCodeAPI();
  api.postMessage({
    type: 'save_conversation',
    ...data
  });
}
```

**Testing:**
- E2E test: Send message → verify save to disk
- Test state restoration on reload

---

#### **Task 5: Extension Bridge Handler** (1 hour)
**Files:**
- `vscode-extension/src/views/provider.ts`

**Handler:**
```typescript
case 'save_conversation':
  // Forward to agent core via JSON-RPC
  this.agentBridge.request('save_conversation', {
    conversationId: message.conversationId,
    messages: message.messages,
    metadata: message.metadata
  });
  break;
```

**Testing:**
- Integration test for message flow

---

#### **Task 6: Create Conversations Panel UI** (4 hours)
**Files:**
- `vscode-extension/webview/src/routes/conversations/+page.svelte` (NEW)
- `vscode-extension/webview/src/lib/components/navigation/AppNavigation.svelte` (UPDATE)

**AppNavigation.svelte changes:**
```typescript
// Add Conversations button
{
  path: '/conversations',
  icon: MessageSquare,
  label: 'Conversations'
}
```

**Conversations page structure:**
```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { sendMessage, onMessage } from '$lib/api/vscode';
  
  let conversations = $state([]);
  let viewMode = $state<'grid' | 'list' | 'timeline'>('timeline');
  let searchQuery = $state('');
  
  onMount(async () => {
    // Request conversation list from agent
    sendMessage({ type: 'list_conversations' });
    
    const unsubscribe = onMessage((event) => {
      if (event.type === 'conversations_list') {
        conversations = event.conversations;
      }
    });
    
    return unsubscribe;
  });
  
  async function loadConversation(id: string) {
    sendMessage({ 
      type: 'load_conversation', 
      conversationId: id 
    });
    // Navigate back to chat
    navigate('/');
  }
  
  async function deleteConversation(id: string) {
    if (confirm('Delete this conversation?')) {
      sendMessage({ 
        type: 'delete_conversation', 
        conversationId: id 
      });
      // Refresh list
      sendMessage({ type: 'list_conversations' });
    }
  }
</script>

<!-- Timeline view implementation (default) -->
<div class="conversations-timeline">
  {#each groupedConversations as group}
    <div class="timeline-group">
      <h3>{group.label}</h3>
      {#each group.conversations as conv}
        <div class="timeline-item" on:click={() => loadConversation(conv.id)}>
          <div class="timeline-marker"></div>
          <div class="timeline-content">
            <h4>{conv.metadata.title}</h4>
            <p class="metadata">
              {conv.messages.length} messages • {formatDate(conv.updated_at)}
            </p>
            {#if conv.metadata.files.length > 0}
              <p class="files">{conv.metadata.files.length} files</p>
            {/if}
          </div>
          <button on:click|stopPropagation={() => deleteConversation(conv.id)}>
            Delete
          </button>
        </div>
      {/each}
    </div>
  {/each}
</div>
```

**Testing:**
- Manual test: Navigate to /conversations, view list
- Test load conversation flow
- Test delete conversation flow

---

#### **Task 7: Conversation Branching Logic** (2 hours)
**Files:**
- `vscode-extension/webview/src/App.svelte`

**Implementation:**
```typescript
// When loading a conversation, track original ID
let loadedConversationId = $state<string | null>(null);
let conversationBranched = $state(false);

function handleLoadConversation(event: AgentEvent) {
  if (event.type === 'conversation_loaded') {
    loadedConversationId = event.conversationId;
    messages = event.messages;
    conversationBranched = false;
    activeConversationId = event.conversationId;
  }
}

// On first new message after loading, create branch
async function handleSend(message: string) {
  if (isProcessing) return;
  
  // If we loaded a conversation and haven't branched yet, create new ID
  if (loadedConversationId && !conversationBranched) {
    const newId = `conv_${Date.now()}_branch`;
    activeConversationId = newId;
    conversationBranched = true;
    
    // Save metadata about parent
    sendMessage({
      type: 'update_conversation_metadata',
      conversationId: newId,
      metadata: {
        parent_conversation_id: loadedConversationId,
        branch_point_message_id: messages[messages.length - 1]?.timestamp
      }
    });
  }
  
  // Continue with normal message handling
  // ... existing code
}
```

**Testing:**
- E2E test: Load conversation → send message → verify new conversation created

---

### **Phase 5b: Enhanced Features (Priority 2) - 3 days**

#### **Task 8: Rich Metadata Capture** (Deferred)
- Git context integration
- User-defined tags
- LLM-generated titles

#### **Task 9: Advanced Views** (Deferred)
- Card Grid view implementation
- Compact List view implementation
- View mode switching

#### **Task 10: Enhanced Actions** (Deferred)
- Rename conversation
- Pin/unpin conversation
- Duplicate conversation
- Export to Markdown/PDF

---

## File Structure

```
vscode-extension/
├── webview/
│   └── src/
│       ├── App.svelte (UPDATED - auto-save logic)
│       ├── routes/
│       │   ├── conversations/
│       │   │   └── +page.svelte (NEW - conversations panel)
│       │   └── gallery/
│       │       └── conversations/
│       │           └── +page.svelte (EXISTING - mockups)
│       └── lib/
│           ├── api/
│           │   └── vscode.ts (UPDATED - new RPC methods)
│           └── types/
│               └── state.ts (NEW - webview state types)
├── src/
│   └── views/
│       └── provider.ts (UPDATED - message handlers)
agent-core/
└── src/
    ├── main.ts (UPDATED - new RPC methods)
    └── storage/
        └── conversation-store.ts (UPDATED - new methods)
shared/
└── types/
    └── state.ts (UPDATED - extended schema)
```

---

## Testing Strategy

### Unit Tests
- [ ] Schema validation (ConversationMetadataSchema)
- [ ] ConversationStore new methods
- [ ] File reference extraction logic

### Integration Tests
- [ ] RPC method calls (extension → agent)
- [ ] Message flow (webview → extension → agent)
- [ ] State restoration (reload webview)

### E2E Tests
- [ ] Send message → auto-save → verify file created
- [ ] Load conversation → verify messages restored
- [ ] Delete conversation → verify file removed
- [ ] Branch conversation → verify new file created
- [ ] Export conversation → verify JSON format

---

## Migration Strategy

### Backward Compatibility
**Existing conversations without metadata:**
- Schema uses `.optional().default({})` for metadata
- Old conversations will auto-upgrade on load
- No manual migration needed

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| State sync conflicts (webview vs. file) | High | Use activeConversationId as source of truth |
| Large conversation files (performance) | Medium | Defer summaries/compression to Phase 5b |
| File I/O errors | Medium | Add error handling and retry logic |
| Conversation ID collisions | Low | Use timestamp + random suffix |

---

## Success Criteria

### MVP (Phase 5a)
- ✅ Conversations auto-save on every message
- ✅ Reloading webview restores active conversation
- ✅ Users can view list of conversations
- ✅ Users can load/delete conversations
- ✅ Branching creates new conversation on edit
- ✅ Conversations include title and file references
- ✅ Export to JSON works

### Full Phase 5
- Deferred to Phase 5b

---

## Timeline

### Day 1
- Morning: Tasks 1-2 (Schema + ConversationStore)
- Afternoon: Task 3 (RPC methods)

### Day 2
- Morning: Task 4 (Auto-save in App.svelte)
- Afternoon: Task 5-6 (Extension handler + Conversations panel)

### Day 3 (Buffer)
- Task 7 (Branching logic)
- Testing and bug fixes

---

## Next Steps

1. **Review this plan** and confirm approach
2. **Create feature branch:** `feature/phase5-conversation-persistence`
3. **Implement Task 1** (schema changes)
4. **Implement sequentially** with testing after each task
5. **Deploy and gather feedback** before Phase 5b

---

## References

- **Phase 5 Requirements:** `docs/vscode-extension-improvement-plan.md` (lines 96-108)
- **Concept Document:** `docs/phase5-conversation-persistence-concepts.md`
- **Gallery Mockups:** `vscode-extension/webview/src/routes/gallery/conversations/+page.svelte`
- **Current ConversationStore:** `agent-core/src/storage/conversation-store.ts`
- **Current Schema:** `shared/types/state.ts`