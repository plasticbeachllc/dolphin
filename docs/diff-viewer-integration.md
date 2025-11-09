# Diff Viewer Integration

## Overview

The Dolphin VSCode extension now includes a beautiful, elegant diff viewer that automatically displays file changes when Claude edits files. This provides users with rich visual feedback about what the agent is doing to their codebase.

## Architecture

### Components

1. **DiffViewer Component** (`vscode-extension/webview/src/lib/components/tools/DiffViewer.svelte`)
   - Standalone, reusable component for rendering file diffs
   - Uses the "Subtle with Border" design (emerald/rose colors with 40-50% opacity)
   - Features:
     - Collapsible diff view with smooth animations
     - Visual statistics bar showing additions vs deletions
     - Dual line numbers (old/new) for precise navigation
     - Syntax-aware highlighting for added/removed/context lines
     - File metadata and change summary
     - Sticky hunk headers for context

2. **ToolCallCard Enhancement** (`vscode-extension/webview/src/lib/components/tools/ToolCallCard.svelte`)
   - Detects file editing tools: `apply_diff`, `write_to_file`, `file_write`, `search_and_replace`, `insert_content`
   - Automatically renders DiffViewer when diff data is available
   - Shows both diff visualization and raw input/output for transparency

### Data Flow

```
Agent Core (MCP Tool Execution)
  ↓
  Generates diff data (FileDiff object)
  ↓
tool_call_completed event with diff field
  ↓
AgentBridge forwards event to VSCode Extension
  ↓
WebviewViewProvider forwards to webview
  ↓
App.svelte receives event, updates message with diff data
  ↓
MessageList passes diff to ToolCallCard
  ↓
ToolCallCard detects file edit tool + diff data
  ↓
DiffViewer renders beautiful diff visualization
```

## Type Definitions

### FileDiff Interface

```typescript
interface FileDiff {
  oldFileName: string;
  newFileName: string;
  additions: number;
  deletions: number;
  hunks: DiffHunk[];
}
```

### DiffHunk Interface

```typescript
interface DiffHunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: string[];  // Lines starting with ' ', '+', or '-'
}
```

### Event Enhancement

The `tool_call_completed` event in `shared/types/events.ts` now includes an optional `diff` field:

```typescript
{
  type: "tool_call_completed";
  toolId: string;
  result: any;
  error?: any;
  executionTime?: number;
  diff?: FileDiff;  // NEW: Diff data for file editing tools
}
```

## Implementation Guide

### For Agent Core / MCP Server Developers

To enable diff visualization for your file editing tools:

1. **Parse the file changes** into a unified diff format
2. **Calculate additions and deletions** (count lines starting with '+' and '-')
3. **Create DiffHunk objects** for each contiguous change block
4. **Include the FileDiff in the tool_call_completed event**:

```typescript
onEvent({
  type: "tool_call_completed",
  toolId: toolCall.id,
  result: { success: true, path: "src/app.ts" },
  executionTime: 125,
  diff: {
    oldFileName: "src/app.ts",
    newFileName: "src/app.ts",
    additions: 6,
    deletions: 1,
    hunks: [{
      oldStart: 1,
      oldLines: 8,
      newStart: 1,
      newLines: 13,
      lines: [
        " export function formatNumber(num: number) {",
        "-  return num.toLocaleString();",
        "+  return new Intl.NumberFormat(\"en-US\").format(num);",
        " }",
        " ",
        "+export function debounce(func: Function, wait: number) {",
        "+  let timeout: NodeJS.Timeout;",
        "+  return (...args: any[]) => clearTimeout(timeout) || (timeout = setTimeout(() => func(...args), wait));",
        "+}"
      ]
    }]
  }
});
```

### Line Format

Each line in `hunk.lines` must start with:
- ` ` (space) - Context line (unchanged)
- `+` - Added line
- `-` - Removed line

## Design Principles

1. **Subtle but Informative**: Uses emerald/rose colors at 40-50% opacity to be professional and easy on the eyes
2. **Information-Rich**: Shows file path, change statistics, line numbers, and file type
3. **Elegant**: Smooth animations, thoughtful spacing, and visual hierarchy
4. **Accessible**: Clear visual distinction between additions, deletions, and context

## Future Enhancements

Potential improvements:
- [ ] Side-by-side diff view option
- [ ] Syntax highlighting within diff content
- [ ] Interactive diff approval/rejection buttons
- [ ] Multi-file diff aggregation
- [ ] Export diff as patch file
- [ ] Inline commenting on diff lines

## Testing

The diff viewer can be tested in the gallery:
1. Navigate to `/gallery` in the webview
2. Scroll to the "DiffViewer" section
3. View the interactive example with collapsible diff content

To test with real file edits:
1. Ask Claude to modify a file in your workspace
2. The agent will use a file editing tool (e.g., `apply_diff`, `write_to_file`)
3. The diff viewer will automatically appear in the tool call card
4. Expand/collapse the diff to inspect changes

## Related Files

- `shared/types/events.ts` - Event type definitions
- `vscode-extension/webview/src/lib/components/tools/DiffViewer.svelte` - Main diff viewer component
- `vscode-extension/webview/src/lib/components/tools/ToolCallCard.svelte` - Tool card with diff integration
- `vscode-extension/webview/src/App.svelte` - Event handling and state management
- `vscode-extension/webview/src/lib/components/chat/MessageList.svelte` - Message rendering
- `vscode-extension/webview/src/routes/gallery/+page.svelte` - Gallery showcase