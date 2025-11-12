# Gallery Architecture

## Overview

The Dolphin webview uses a **dual-mode build system** that supports both development and production:

1. **Development Mode** - Full SvelteKit with file-based routing (`npm run dev`)
2. **Production Mode** - Standalone Svelte bundle (`npm run build`)

## Gallery Routes

Gallery routes live in `src/routes/gallery/` and include:

- `/gallery` - Main gallery with tabbed interface (Components, Animations, Loading States, Featured)
- `/gallery/conversations` - Conversation history browser

## Development vs Production

### Development (SvelteKit)
- Uses file-based routing via `src/routes/`
- Full gallery accessible at `http://localhost:5173/gallery`
- Hot module replacement for rapid iteration
- Navigation via `AppNavigation.svelte` and SvelteKit routing

### Production (Standalone Svelte)
- Uses `src/main.ts` → `src/App.svelte`
- Manual view routing via `currentView` state variable
- ConversationsGallery is **included** in production bundle (imported in App.svelte line 10)
- Gallery route accessible via `AppNavigation` but limited to conversations view

## Module Resolution

All shared types use the `@shared` alias defined in:
- `vite.config.webview.ts` (line 46): `'@shared': path.resolve(__dirname, '../../shared')`
- `svelte.config.js` (line 26): `'@shared': '../../shared'`

### Import Pattern
```typescript
// ✅ Correct - uses alias
import type { AgentEvent } from '@shared/types/events';

// ❌ Incorrect - relative path
import type { AgentEvent } from '../../../../../shared/types/events';
```

## Gallery Component Status

| Component | Dev | Prod | Notes |
|-----------|-----|------|-------|
| `/gallery` (main) | ✅ | ❌ | SvelteKit route only |
| `/gallery/conversations` | ✅ | ✅ | Imported in App.svelte |
| `AnimationGallery.svelte` | ✅ | ❌ | Dev showcase only |
| `LoadingStates.svelte` | ✅ | ❌ | Dev showcase only |
| `AnimationLibrary.svelte` | ✅ | ✅ | Reusable animation components |

## Animation System

The animation system consists of:

### 1. Design Documentation
- `docs/DesignTokens.md` - OKLCH color system, spacing, typography
- `docs/InteractionPatterns.md` - UX patterns, accessibility guidelines

### 2. Reusable Components (`AnimationLibrary.svelte`)
- Custom actions: `StreamingText`, `ProgressiveReveal`, `CounterAnimation`
- Snippets: `ThinkingDots`, `ShimmerLoader`, `SlideInCard`, etc.
- Used throughout production app

### 3. Gallery Showcases (dev-only)
- `AnimationGallery.svelte` - Visual showcase with reset buttons
- `LoadingStates.svelte` - Loading pattern examples
- Main gallery route at `/gallery` with tabs

## CSS Animations

All animations defined in `src/app.css` (lines 147-230):

```css
.animate-pulse-glow      /* Breathing glow effect */
.animate-typing-dot      /* Bouncing dots */
.animate-slide-in-up     /* Slide up entrance */
.animate-shimmer         /* Skeleton loading shimmer */
.animate-breathe         /* Subtle pulsing */
.animate-fade-in         /* Opacity transition */
.animate-bounce-subtle   /* Gentle bounce */
```

## Recent Fixes

1. ✅ Loading shimmer now visible (3 skeleton bars with proper background)
2. ✅ Conversations gallery import fixed (uses `@shared` alias)
3. ✅ App.svelte import updated to use `@shared` alias
4. ✅ All Svelte 5 warnings resolved

## Best Practices

1. **Use `@shared` alias** for all shared type imports
2. **Gallery showcases are dev-only** - only reference code, not full components
3. **AnimationLibrary snippets** are production-ready and reusable
4. **Keep animations subtle** - follow guidelines in InteractionPatterns.md