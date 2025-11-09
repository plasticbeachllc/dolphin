# Dolphin Extension Webview

Modern Svelte-based UI for the Dolphin VSCode extension.

## Overview

This is the webview component of the Dolphin VSCode extension, built with SvelteKit and shadcn/ui. It provides the chat interface, settings panel, and component gallery.

## Technology Stack

- **SvelteKit** - Full-stack framework for building the UI
- **Svelte** - Reactive UI components
- **TypeScript** - Type-safe development
- **shadcn/ui** - Accessible UI components
- **Tailwind CSS** - Utility-first styling
- **Bun** - Fast JavaScript runtime and package manager

## Project Structure

```
webview/
├── src/
│   ├── routes/
│   │   ├── +page.svelte        # Main chat interface
│   │   ├── settings/
│   │   │   └── +page.svelte    # Settings page
│   │   └── gallery/
│   │       └── +page.svelte    # Component gallery (dev tool)
│   ├── lib/
│   │   ├── components/
│   │   │   ├── ui/             # shadcn/ui components
│   │   │   ├── ChatMessage.svelte
│   │   │   ├── ChatInput.svelte
│   │   │   ├── ToolCallCard.svelte
│   │   │   ├── AuthStatus.svelte
│   │   │   └── ...
│   │   ├── stores/
│   │   │   └── messages.ts     # Message state management
│   │   └── types.ts            # TypeScript type definitions
│   └── app.html                # HTML template
├── static/                     # Static assets
├── svelte.config.js            # SvelteKit configuration
└── package.json
```

## Development

### Prerequisites

- **Bun** ≥ 1.0 - [Install](https://bun.sh/install)

### Setup

```bash
# Install dependencies
bun install
```

### Development Server

Start the development server with hot reload:

```bash
bun run dev
```

Open http://localhost:5173 to view the standalone webview.

**Note**: For full functionality (Agent Core integration), run the webview within the VSCode extension instead.

### Build for Production

Build the webview for embedding in the VSCode extension:

```bash
bun run build
```

Output is generated in `build/` directory and consumed by the extension.

### Preview Production Build

Preview the production build locally:

```bash
bun run preview
```

## Features

### Main Pages

**Chat Page** (`/`)
- Message history with user/assistant/system messages
- Real-time streaming responses
- Tool call visualization
- Auto-scroll functionality
- Markdown rendering with code highlighting

**Settings Page** (`/settings`)
- Authentication status display
- Refresh auth status
- Configuration options

**Gallery Page** (`/gallery`)
- Developer tool for testing UI components
- Preview all component states
- Useful for UI development and testing

### Key Components

**ChatMessage.svelte**
- Displays individual messages
- Supports user, assistant, and system roles
- Markdown rendering
- Syntax highlighting for code blocks

**ChatInput.svelte**
- Multi-line text input
- Submit on Enter (Shift+Enter for new line)
- Auto-focus and keyboard shortcuts

**ToolCallCard.svelte**
- Visualizes tool executions (e.g., KB searches)
- Shows running, success, and error states
- Displays tool results

**AuthStatus.svelte**
- Real-time authentication status display
- Color-coded badges (CLI/API/none)
- Contextual help text
- Manual refresh button

## Communication with Extension

The webview communicates with the VSCode extension via the `vscode` API:

```typescript
// Extension → Webview
window.addEventListener('message', (event) => {
  const message = event.data;
  // Handle messages from extension
});

// Webview → Extension
vscode.postMessage({
  type: 'sendMessage',
  payload: { content: 'Hello!' }
});
```

Message types:

- `sendMessage` - User sends a chat message
- `agentEvent` - Agent Core event (task updates, tool calls, etc.)
- `getAuthStatus` - Request auth status from Agent Core
- `authStatusResponse` - Auth status response

See `src/lib/stores/messages.ts` for message handling logic.

## Styling

### Tailwind CSS

Utility-first CSS framework for rapid UI development:

```svelte
<div class="flex flex-col gap-4 p-4 bg-background text-foreground">
  <!-- Content -->
</div>
```

### shadcn/ui Components

Pre-built accessible components:

```svelte
<script>
  import { Button } from '$lib/components/ui/button';
  import { Card } from '$lib/components/ui/card';
</script>

<Card>
  <Button variant="outline">Click me</Button>
</Card>
```

### Theme System

Uses CSS variables for theming:

```css
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --primary: 222.2 47.4% 11.2%;
  /* ... */
}
```

## Testing

### Component Gallery

Use the gallery page to visually test components:

1. Run `bun run dev`
2. Navigate to http://localhost:5173/gallery
3. View all component states and variations

### VSCode Extension Testing

To test within the extension:

1. Build webview: `bun run build`
2. Open parent `vscode-extension` folder in VSCode
3. Press F5 to launch Extension Development Host
4. Open Dolphin sidebar

## Build Configuration

### SvelteKit Adapter

Uses `@sveltejs/adapter-static` for static site generation:

```javascript
// svelte.config.js
import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: undefined
    })
  }
};
```

### TypeScript

Type checking is enabled via `tsconfig.json`. Run type checking:

```bash
bun run check
```

## Troubleshooting

### Build fails

**Solution**: Clear build artifacts and rebuild:

```bash
rm -rf build .svelte-kit
bun run build
```

### Components not styled

**Cause**: Tailwind CSS not processing styles.

**Solution**: Restart dev server or rebuild.

### Module not found errors

**Cause**: Dependencies not installed.

**Solution**:

```bash
rm -rf node_modules
bun install
```

## Contributing

1. Make changes to components in `src/lib/components/`
2. Test in gallery page or extension
3. Run type checking: `bun run check`
4. Build to verify: `bun run build`
5. Submit pull request

## Links

- [SvelteKit Documentation](https://kit.svelte.dev/)
- [Svelte Documentation](https://svelte.dev/)
- [shadcn/ui](https://ui.shadcn.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [VSCode Extension](../README.md)
- [Main Project](../../README.md)

---

**Need Help?** See the [VSCode Extension README](../README.md) or open an issue at https://github.com/plasticbeachllc/dolphin/issues
