# Changelog - Dolphin VSCode Extension

All notable changes to the Dolphin VSCode extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-11-12

### Added

#### 🎨 Core Extension Features

- **Dual Authentication System**
  - Claude CLI integration for subscription-based usage (no API costs)
  - Direct Anthropic API key support as fallback
  - Automatic authentication detection and status display
  - OAuth workflow integration for Claude Code

- **Modern Webview Interface**
  - Beautiful SvelteKit-based UI with shadcn/ui component library
  - Real-time token-by-token streaming from Claude
  - VSCode theme integration with dark/light mode support
  - Multiple routes: Chat, Settings, Gallery, Profile, Tools, Functions
  - Component gallery for development and testing
  - Interactive plan timeline visualization with animated status indicators

- **Rich Editor Integration**
  - Context menu commands: "Ask About Selection", "Refactor Selection", "Ask About File", "Ask About Folder"
  - Keyboard shortcuts (Cmd+L/Ctrl+L to focus chat input)
  - Diff viewer with syntax highlighting and side-by-side/unified modes
  - Copy functionality for code blocks and diffs
  - File and folder context injection

- **Conversation Management**
  - Persistent conversation history in TOML format
  - Conversation branching support
  - Message metadata tracking with hybrid token counting
  - Session restoration across VSCode restarts
  - Comprehensive test suite (52+ TypeScript tests)

#### ♿ Accessibility Standards (WCAG 2.1 AA Compliance)

- **Comprehensive Keyboard Navigation**
  - Full keyboard accessibility for all extension features
  - Logical tab order throughout the interface
  - Focus indicators with 3:1 minimum contrast ratio
  - Standard keyboard shortcuts (Escape to close, Enter to submit)
  - No keyboard traps in any UI components

- **Screen Reader Support**
  - ARIA labels and landmarks for all interactive elements
  - Semantic HTML structure with proper heading hierarchy
  - Live regions for dynamic content announcements
  - Context announcements for tool calls and status changes
  - Tested with NVDA, JAWS, VoiceOver, and Orca screen readers

- **Visual Accessibility**
  - 4.5:1 minimum contrast ratio for normal text
  - 3:1 minimum contrast ratio for UI components and focus indicators
  - VSCode theme token integration for consistent, accessible colors
  - High contrast mode support
  - Color-independent information display (no meaning by color alone)
  - Reduced motion support (`prefers-reduced-motion` media query)

#### 🔄 Dual-Path Indexing (File Watch + Git Diff)

- **Real-Time File Watch System**
  - Live file change detection via VSCode file system API
  - Crash-proof pending changes queue stored in SQLite
  - Four auto-sync modes:
    - **Off** - Manual indexing only
    - **Manual** - User confirmation required for each sync
    - **Smart** (default) - Auto-sync during idle periods (30+ seconds)
    - **Aggressive** - Immediate incremental indexing on every change
  - Mid-index change detection and automatic re-queuing
  - Progress tracking with current file display
  - Configurable debounce timing

- **Git-Aware Incremental Indexing**
  - `git diff` integration for efficient change detection
  - Commit SHA and branch tracking with each indexed chunk
  - Drift detection for offline/background changes
  - Post-commit hook support for automatic indexing
  - Only reindexes changed files for maximum efficiency
  - Graph pruning on file deletions to maintain data integrity

- **Robust Architecture**
  - TypeScript (VSCode) handles detection and triggers indexing
  - Python (FastAPI) handles processing and persistence
  - JSON-RPC communication over stdio with proper framing
  - Automatic status updates on completion
  - Path normalization before API sync
  - Comprehensive test coverage for all sync phases

#### 📊 Plan Visualization and UI Styling

- **Plan Timeline Visualization**
  - Interactive draggable timeline component (`PlanTimeline.svelte`)
  - Visual step indicators with dynamic status colors
  - Animated pulsing for currently running steps
  - Connected step visualization with progress lines
  - Status tracking: pending, running, completed, error
  - Expandable/collapsible step details

- **Advanced Diff Viewer**
  - Side-by-side and unified diff display modes (`DiffViewer.svelte`)
  - Syntax highlighting for all supported languages
  - Line-by-line change visualization with add/delete markers
  - Copy functionality for code selections
  - Binary file and size guards

- **Tool Call Visualization**
  - Real-time tool execution cards (`ToolCallCard.svelte`)
  - Knowledge base search visualization with result counts
  - Success/error/loading state indicators
  - Expandable/collapsible tool result displays
  - Metadata display (latency, result count, status)

- **Rich Message Components**
  - Markdown rendering with code syntax highlighting
  - Code blocks with one-click copy buttons
  - User/assistant/system message styling
  - Error alerts with contextual information
  - Confirmation dialogs with accessible keyboard controls
  - Loading states with spinners and skeleton screens

- **Component Library (shadcn/ui)**
  - 20+ accessible, reusable UI components:
    - Alert, Alert Dialog, Avatar, Badge
    - Button, Card, Checkbox, Collapsible
    - Dialog, Input, Label, Navigation Menu
    - Progress, Radio Group, Scroll Area
    - Separator, Skeleton, Tabs, Textarea
  - Tailwind CSS utility-first styling
  - Consistent design tokens across all components
  - Typography system with semantic hierarchy
  - Responsive layout utilities

- **Theme System**
  - VSCode theme token integration for native look and feel
  - Seamless dark/light theme switching
  - High contrast mode support
  - Custom color palette with WCAG-compliant contrast ratios
  - CSS custom properties for theming

### Changed

- **IPC Architecture Improvements**
  - JSON-RPC framing alignment in AgentCore stdio communication
  - Improved error propagation between TypeScript and Python layers
  - Event-driven status updates for better responsiveness
  - Robust handling of process lifecycle and crashes

- **File Sync Architecture**
  - Python backend now auto-marks changes as processed (Phase 2)
  - Path normalization before API synchronization
  - Improved crash recovery with persistent queues
  - Better handling of rapid file changes

### Fixed

- **File Sync and Indexing**
  - Diff application on empty/new files now works correctly
  - File watcher path normalization prevents duplicate processing
  - Metadata updates now persist correctly during conversation saves
  - Indexing task async handling and TypeScript typings corrected

### Technology Stack

- **VSCode Extension API** - Editor integration
- **Bun** - Fast JavaScript runtime for Agent Core
- **Anthropic SDK** - Claude API client
- **SvelteKit** - Full-stack web framework
- **Svelte 5** - Reactive UI components
- **Tailwind CSS** - Utility-first styling
- **shadcn/ui** - Accessible component library
- **Zod** - Runtime type validation

### Migration Notes

This is the first production release of the Dolphin VSCode extension.

For detailed documentation, visit the `/docs` directory in the main repository.

---

## [0.0.1] - 2025-11-01

### Added

- Initial development release
- Basic Claude integration
- Simple chat interface
- Knowledge base integration
