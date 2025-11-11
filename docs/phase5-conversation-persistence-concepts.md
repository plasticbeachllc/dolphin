# Phase 5: Conversation Persistence & Sessions — UI Concepts & Key Questions

**Version:** 0.1  
**Date:** 2025-11-09  
**Status:** Design Review / Mockup Phase  

---

## Overview

Phase 5 of the VSCode Extension Improvement Plan focuses on **conversation persistence and multi-session support**. This document outlines the UI concepts we've mocked up in the `/gallery/conversations` route and surfaces critical questions that need answers before implementation.

---

## Implementation Requirements (from Plan)

### Phase 5 Core Requirements:
1. **Persist chat history in webview state**
   - Save messages via `setState` and restore on mount
   - Files: `vscode-extension/webview/src/lib/api/vscode.ts:57,66`, `webview/src/App.svelte`

2. **Multi-session support (optional, phase 2)**
   - Add a `TreeView` for "Conversations" with create/rename/pin/delete
   - Store in `globalState`

### Acceptance Criteria:
- Reloading the view/window preserves the current conversation
- Users can create and switch between named sessions

---

## Backend Infrastructure (Already Exists)

### ConversationStore (`agent-core/src/storage/conversation-store.ts`)
The backend already has a robust conversation persistence layer:

- **Storage format:** TOML files in `.dolphin/state/conversations/`
- **Methods available:**
  - `saveConversation(id, messages, metadata)` - Persist conversation to disk
  - `loadConversation(id)` - Restore conversation from disk
  - `listConversations()` - Get all conversations with metadata
  - `deleteConversation(id)` - Remove conversation
  - `getLatestConversation()` - Get most recent conversation
  - `exportConversation(id)` - Export to portable format
  - `importConversation(data)` - Import from exported data

### ConversationMessage Schema (`shared/types/state.ts`)
```typescript
{
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  pinned?: boolean;
}
```

**Gap:** The existing schema doesn't include rich metadata we'd want for the UI mockups (tags, git context, message counts). This needs to be addressed.

---

## UI Concepts Mocked Up

### Location
**Route:** `/gallery/conversations` (navigable from main gallery page)

### Three Layout Modes

#### 1. **Card Grid View** (Default)
- **Visual:** 2-3 column responsive grid of conversation cards
- **Information density:** High - shows full preview text, all metadata
- **Best for:** Browsing and visual scanning of conversations
- **Features:**
  - Large preview cards with hover states
  - Pinned section at top (separate from chronological list)
  - Badge indicators for tags, git branches, message counts
  - Action buttons on hover (rename, pin, delete, export)
  - Grouped by time: Today, Yesterday, Last Week, Older

#### 2. **Compact List View**
- **Visual:** Single column dense list
- **Information density:** Medium - condensed metadata, truncated previews
- **Best for:** Quick scanning and searching through many conversations
- **Features:**
  - Avatar/icon + title + metadata in single row
  - Inline badges for quick identification
  - Faster scanning with less scrolling
  - Same grouping and pinning as grid view

#### 3. **Timeline View**
- **Visual:** Chronological timeline with connecting lines
- **Information density:** Medium-High - emphasizes temporal relationships
- **Best for:** Understanding conversation history flow over time
- **Features:**
  - Visual timeline with date markers
  - Shows relationships between conversations
  - Useful for tracking project evolution
  - Could show branching/forking of conversations

### Common Features Across All Views
- **Search bar** with real-time filtering
- **Pinned conversations** section (always visible at top)
- **Relative timestamps** ("2 hours ago", "Yesterday")
- **Metadata badges:**
  - Tags (user-defined, e.g., "bug-fix", "refactor")
  - Git context (branch name, commit hash)
  - Message count
  - File count (if applicable)
- **Action buttons** (shown on hover):
  - Rename conversation
  - Pin/Unpin to top
  - Export to file
  - Duplicate conversation
  - Delete conversation

---

## Critical Questions for Decision-Making

### 1. **Storage & State Management**

**Q1.1:** Where should conversation state live?
- **Option A:** Extension `globalState` (current plan) - survives reload, limited to 10MB
- **Option B:** Extension `workspaceState` - per-workspace, auto-cleanup
- **Option C:** File-based (`.dolphin/state/conversations/`) - already implemented in backend
- **Option D:** Hybrid - active session in memory/state, archive to files

**Trade-offs:**
- `globalState` = global across all workspaces, survives reload, but 10MB limit
- `workspaceState` = per-project isolation, auto-cleanup on workspace delete
- File-based = unlimited storage, survives extension uninstall, already working
- Hybrid = best UX but more complex sync logic

**Recommendation:** Hybrid approach - use existing file-based ConversationStore for persistence, cache active conversation in webview state for performance.

---

**Q1.2:** How do we sync state between webview and extension?
- **Current:** Webview has `vscode.setState()` / `getState()` for persistence
- **Challenge:** Need bidirectional sync between webview state and ConversationStore
- **Options:**
  - On webview mount: Load from ConversationStore → `setState()`
  - On message send: Update both webview state AND ConversationStore
  - On navigation/switch: Save current to store, load new from store

**Decision needed:** Sync strategy and conflict resolution approach.

---

### 2. **UI/UX Decisions**

**Q2.1:** Which layout view should be the default?
- **Card Grid** - Most visual, good for smaller collections
- **Compact List** - Most efficient, good for power users
- **Timeline** - Most contextual, good for project-based work

**Decision needed:** Default view mode (should be user-configurable).

---

**Q2.2:** How should users navigate to conversations?
- **Option A:** Click opens conversation in current chat panel (replace current)
- **Option B:** Double-click to open, single-click to preview
- **Option C:** Always prompt before replacing unsaved conversation
- **Option D:** Side-by-side view (split panel)

**Current mockup:** Option A (single click replaces)

**Decision needed:** Navigation pattern and unsaved state handling.

---

**Q2.3:** Where should the "Conversations" UI live?
- **Option A:** Dedicated TreeView in Activity Bar (plan suggests this)
- **Option B:** Panel within webview (current gallery mockup approach)
- **Option C:** Command Palette only (minimal UI)
- **Option D:** Both TreeView AND webview panel

**Trade-offs:**
- TreeView = Native VS Code pattern, always visible, limited styling
- Webview panel = Rich UI, consistent with chat, requires navigation
- Command Palette = Minimal but low discoverability
- Both = Best UX but more implementation work

**Decision needed:** Primary UI surface for conversation management.

---

### 3. **Metadata & Enrichment**

**Q3.1:** What metadata should we capture automatically?
- [x] Timestamp (already in schema)
- [x] Message count (derivable)
- [ ] **Git context** (branch, commit) - need to implement
- [ ] **Tags** (user-defined or auto-generated) - need to implement
- [ ] **File references** (which files discussed) - need to implement
- [ ] **Tool usage** (which tools were called) - need to implement
- [ ] **Token/cost tracking** - need to implement

**Gap:** Current schema only has basic message data. Need extended metadata.

**Decision needed:** Which metadata to implement and how to capture it.

---

**Q3.2:** Should we auto-generate conversation titles?
- **Current:** ConversationStore uses timestamp-based IDs
- **Options:**
  - User must provide title (explicit)
  - Auto-generate from first message (implicit)
  - LLM-generated summary title (smart but costly)
  - Hybrid: Auto-suggest, user can edit

**Decision needed:** Title generation strategy.

---

**Q3.3:** How should tags work?
- **Manual only** - User adds tags via UI
- **Auto-suggested** - LLM suggests tags based on content
- **Both** - Mix of manual and auto-suggested

**Decision needed:** Tag creation and management approach.

---

### 4. **Session Management**

**Q4.1:** What happens to the "active" conversation?
- **Auto-save:** Every message automatically persists
- **Manual save:** User must explicitly save conversation
- **Smart save:** Save on navigation, close, or inactivity

**Recommendation:** Auto-save every message (already possible with ConversationStore).

---

**Q4.2:** How do we handle conversation forking/branching?
- **Scenario:** User loads old conversation, sends new message
- **Options:**
  - Overwrite the old conversation (destructive)
  - Create new branch (preserves history)
  - Prompt user to choose
  - Always create new conversation from loaded state

**Decision needed:** Forking behavior when editing historical conversations.

---

**Q4.3:** Should we support conversation merging/combining?
- **Use case:** User has multiple related conversations
- **Complexity:** High - need to handle message ordering, duplicates
- **Value:** Medium - nice-to-have but not critical

**Decision needed:** Is this in scope for Phase 5?

---

### 5. **Data Management**

**Q5.1:** How do we handle conversation limits/cleanup?
- **Unlimited storage?** (risky for long-term users)
- **Auto-archive old conversations?** (after X days/months)
- **Manual cleanup only?** (relies on user discipline)
- **Size-based limits?** (e.g., max 1000 conversations)

**Decision needed:** Retention and cleanup policy.

---

**Q5.2:** What export/import formats should we support?
- **JSON** - Full fidelity, machine-readable
- **Markdown** - Human-readable, portable
- **PDF** - Shareable, read-only
- **HTML** - Rich formatting, embeddable

**Current mockup:** Shows "Export" button but doesn't specify format.

**Decision needed:** Export format(s) and import capabilities.

---

**Q5.3:** Should we sync conversations across machines?
- **Out of scope for Phase 5** - but worth considering for future
- **Options:** VS Code Settings Sync, custom cloud sync, file-based (Git)

---

### 6. **Implementation Strategy**

**Q6.1:** Phased rollout approach?
- **Phase 5a (MVP):** Basic persistence + simple list view
- **Phase 5b:** Multi-session + TreeView
- **Phase 5c:** Rich metadata + advanced views

**Recommendation:** Start with MVP, iterate based on feedback.

---

**Q6.2:** Do we need backward compatibility?
- **Question:** Are there existing users with conversation data?
- **If yes:** Need migration strategy from old format to new
- **If no:** Clean slate implementation

**Decision needed:** Migration requirements (if any).

---

**Q6.3:** Testing strategy for persistence?
- **Unit tests:** ConversationStore methods (already exist)
- **Integration tests:** Webview ↔ Extension ↔ Store sync
- **E2E tests:** User workflows (create, load, delete, search)
- **Edge cases:** Concurrent modifications, corrupt data, storage limits

**Decision needed:** Test coverage priorities.

---

## Implementation Recommendations

### Priority 1 (MVP - Phase 5a)
1. **Basic auto-save:** Every message persists via ConversationStore
2. **Webview state restoration:** Mount loads latest conversation
3. **Simple list view:** Command to show all conversations (Command Palette)
4. **Core actions:** Load, delete conversations

**Estimated effort:** 1-2 days

---

### Priority 2 (Full Phase 5)
1. **TreeView integration:** Native sidebar for conversations
2. **Rich metadata:** Capture git context, tags, file references
3. **Advanced UI:** Multiple view modes, search, filtering
4. **Session actions:** Rename, pin, export, duplicate

**Estimated effort:** 2-3 days (on top of MVP)

---

### Priority 3 (Future Enhancements)
1. **Conversation branching/forking**
2. **LLM-generated titles and tags**
3. **Advanced search** (semantic search using KB)
4. **Cloud sync** (via VS Code Settings Sync or custom)
5. **Conversation analytics** (token usage, tool usage over time)

**Estimated effort:** 5+ days (defer to future phases)

---

## Mock Data Structure (for Reference)

The gallery mockup uses this enhanced structure:

```typescript
interface ConversationMockup {
  id: string;
  title: string;
  preview: string;
  timestamp: number;
  messages: number;
  tags: string[];
  gitContext?: {
    branch: string;
    commit?: string;
  };
  pinned: boolean;
}
```

**Note:** This is richer than the current schema. We need to decide which fields to add to the real implementation.

---

## Next Steps

1. **Review this document** and answer the key questions above
2. **Prioritize features** - what's in MVP vs. future phases
3. **Define extended schema** - what metadata do we capture
4. **Choose UI approach** - TreeView, webview panel, or both
5. **Prototype MVP** - basic persistence + simple UI
6. **Iterate** based on user feedback

---

## Gallery Mockups Location

**Route:** `vscode-extension/webview/src/routes/gallery/conversations/+page.svelte`

**Access:** 
1. Open extension webview
2. Navigate to `/gallery` 
3. Click "Conversation Persistence Mockups" in featured section
4. Explore three layout modes: Grid, List, Timeline

**Purpose:** Visual reference for UI patterns before implementation decisions.

---

## References

- **Improvement Plan:** `docs/vscode-extension-improvement-plan.md` (Phase 5, lines 96-108)
- **ConversationStore:** `agent-core/src/storage/conversation-store.ts`
- **Message Schema:** `shared/types/state.ts`
- **Webview API:** `vscode-extension/webview/src/lib/api/vscode.ts`
- **Gallery Mockup:** `vscode-extension/webview/src/routes/gallery/conversations/+page.svelte`