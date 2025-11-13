# Design Tokens

This document defines the core design tokens for the Dolphin UI, built on the shadcn-svelte component library and Tailwind CSS v4.

## Color System

### Semantic Color Variables

All colors are defined using OKLCH color space for better perceptual uniformity and wider color gamut support.

#### Light Theme

```css
:root {
  /* Core colors */
  --background: oklch(1 0 0); /* Pure white */
  --foreground: oklch(0.129 0.042 264.695); /* Deep slate */
  --card: oklch(1 0 0); /* Pure white */
  --card-foreground: oklch(0.129 0.042 264.695); /* Deep slate */

  /* Interactive elements */
  --primary: oklch(0.208 0.042 265.755); /* Deep blue */
  --primary-foreground: oklch(0.984 0.003 247.858); /* Off-white */
  --secondary: oklch(0.968 0.007 247.896); /* Light gray */
  --secondary-foreground: oklch(0.208 0.042 265.755); /* Deep blue */

  /* States */
  --muted: oklch(0.968 0.007 247.896); /* Light gray */
  --muted-foreground: oklch(0.554 0.046 257.417); /* Medium gray */
  --accent: oklch(0.968 0.007 247.896); /* Light gray */
  --accent-foreground: oklch(0.208 0.042 265.755); /* Deep blue */
  --destructive: oklch(0.577 0.245 27.325); /* Red */

  /* Borders and inputs */
  --border: oklch(0.929 0.013 255.508); /* Light border */
  --input: oklch(0.929 0.013 255.508); /* Light input border */
  --ring: oklch(0.704 0.04 256.788); /* Focus ring */

  /* Data visualization (charts) */
  --chart-1: oklch(0.646 0.222 41.116); /* Orange */
  --chart-2: oklch(0.6 0.118 184.704); /* Cyan */
  --chart-3: oklch(0.398 0.07 227.392); /* Blue */
  --chart-4: oklch(0.828 0.189 84.429); /* Yellow-green */
  --chart-5: oklch(0.769 0.188 70.08); /* Yellow */
}
```

#### Dark Theme

```css
.dark {
  /* Core colors */
  --background: oklch(0.2 0.015 265); /* Dark slate */
  --foreground: oklch(0.95 0.003 247.858); /* Off-white */
  --card: oklch(0.25 0.015 265); /* Slightly lighter slate */
  --card-foreground: oklch(0.95 0.003 247.858); /* Off-white */

  /* Interactive elements */
  --primary: oklch(0.929 0.013 255.508); /* Light gray */
  --primary-foreground: oklch(0.208 0.042 265.755); /* Deep blue */
  --secondary: oklch(0.279 0.041 260.031); /* Medium slate */
  --secondary-foreground: oklch(0.984 0.003 247.858); /* Off-white */

  /* States */
  --muted: oklch(0.279 0.041 260.031); /* Medium slate */
  --muted-foreground: oklch(0.704 0.04 256.788); /* Light gray */
  --accent: oklch(0.279 0.041 260.031); /* Medium slate */
  --accent-foreground: oklch(0.984 0.003 247.858); /* Off-white */
  --destructive: oklch(0.704 0.191 22.216); /* Bright red */

  /* Borders and inputs */
  --border: oklch(1 0 0 / 10%); /* Transparent white */
  --input: oklch(1 0 0 / 15%); /* Transparent white */
  --ring: oklch(0.551 0.027 264.364); /* Blue-gray */

  /* Data visualization (charts) */
  --chart-1: oklch(0.488 0.243 264.376); /* Purple */
  --chart-2: oklch(0.696 0.17 162.48); /* Teal */
  --chart-3: oklch(0.769 0.188 70.08); /* Yellow */
  --chart-4: oklch(0.627 0.265 303.9); /* Magenta */
  --chart-5: oklch(0.645 0.246 16.439); /* Orange */
}
```

### Usage in Components

Access colors using Tailwind utility classes:

```svelte
<!-- Background colors -->
<div class="bg-background text-foreground">...</div>
<div class="bg-card text-card-foreground">...</div>
<div class="bg-primary text-primary-foreground">...</div>

<!-- Border colors -->
<div class="border border-border">...</div>

<!-- State colors -->
<div class="bg-muted text-muted-foreground">...</div>
<div class="bg-accent text-accent-foreground">...</div>
<div class="bg-destructive">...</div>

<!-- Chart colors -->
<div class="fill-chart-1">...</div>
<div class="stroke-chart-2">...</div>
```

## Spacing Scale

Using Tailwind's default spacing scale (1 unit = 0.25rem = 4px):

### Common Spacing Values

| Token    | Value   | Pixels | Usage            |
| -------- | ------- | ------ | ---------------- |
| `gap-1`  | 0.25rem | 4px    | Tight spacing    |
| `gap-2`  | 0.5rem  | 8px    | Default gap      |
| `gap-3`  | 0.75rem | 12px   | Medium gap       |
| `gap-4`  | 1rem    | 16px   | Standard spacing |
| `gap-6`  | 1.5rem  | 24px   | Large spacing    |
| `gap-8`  | 2rem    | 32px   | XL spacing       |
| `gap-12` | 3rem    | 48px   | Section spacing  |

### Component-Specific Spacing

```css
/* Card padding */
.card-padding-sm: p-3    /* 12px */
.card-padding-md: p-4    /* 16px */
.card-padding-lg: p-6    /* 24px */

/* List item spacing */
.list-gap: gap-2         /* 8px between items */
.list-section-gap: gap-6 /* 24px between sections */

/* Grid layouts */
.grid-gap-sm: gap-2      /* 8px */
.grid-gap-md: gap-4      /* 16px */
.grid-gap-lg: gap-6      /* 24px */
```

## Border Radius

Configured via `--radius` variable (default: 0.625rem = 10px):

```css
:root {
  --radius: 0.625rem; /* Base radius */
  --radius-sm: calc(var(--radius) - 4px); /* Small: 6px */
  --radius-md: calc(var(--radius) - 2px); /* Medium: 8px */
  --radius-lg: var(--radius); /* Large: 10px */
  --radius-xl: calc(var(--radius) + 4px); /* XL: 14px */
}
```

### Usage

```svelte
<!-- Tailwind utilities -->
<div class="rounded-sm">...</div>   <!-- 6px -->
<div class="rounded-md">...</div>   <!-- 8px -->
<div class="rounded-lg">...</div>   <!-- 10px -->
<div class="rounded-xl">...</div>   <!-- 14px -->
<div class="rounded-full">...</div> <!-- Fully rounded -->
```

## Typography

### Font Families

```css
/* System font stack (default) */
font-family:
  -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell",
  "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif;

/* Monospace (for code) */
font-family: "Monaco", "Menlo", "Ubuntu Mono", "Consolas", "source-code-pro", monospace;
```

### Font Sizes

| Class       | Size            | Line Height | Usage             |
| ----------- | --------------- | ----------- | ----------------- |
| `text-xs`   | 0.75rem (12px)  | 1rem        | Captions, labels  |
| `text-sm`   | 0.875rem (14px) | 1.25rem     | Body text (small) |
| `text-base` | 1rem (16px)     | 1.5rem      | Body text         |
| `text-lg`   | 1.125rem (18px) | 1.75rem     | Large body        |
| `text-xl`   | 1.25rem (20px)  | 1.75rem     | Headings (small)  |
| `text-2xl`  | 1.5rem (24px)   | 2rem        | Headings          |
| `text-3xl`  | 1.875rem (30px) | 2.25rem     | Large headings    |

### Font Weights

| Class           | Weight | Usage           |
| --------------- | ------ | --------------- |
| `font-normal`   | 400    | Body text       |
| `font-medium`   | 500    | Emphasized text |
| `font-semibold` | 600    | Subheadings     |
| `font-bold`     | 700    | Headings        |

## Animation Timing

### Duration

```css
/* Tailwind utilities */
duration-75   /* 75ms - Instant feedback */
duration-100  /* 100ms - Micro-interactions */
duration-150  /* 150ms - Quick transitions (default) */
duration-200  /* 200ms - Standard transitions */
duration-300  /* 300ms - Emphasized transitions */
duration-500  /* 500ms - Slow transitions */
duration-700  /* 700ms - Very slow transitions */
duration-1000 /* 1000ms - Animations */
```

### Timing Functions

```css
ease-linear    /* Linear: constant speed */
ease-in        /* Ease-in: slow start */
ease-out       /* Ease-out: slow end (preferred for exits) */
ease-in-out    /* Ease-in-out: slow start and end (preferred for entrances) */
```

### Recommended Usage

```svelte
<!-- Button hover (instant) -->
<button class="transition-colors duration-100 hover:bg-accent">

<!-- Card hover (quick) -->
<div class="transition-all duration-150 hover:scale-105">

<!-- Sheet slide-in (standard) -->
<div class="transition-transform duration-200 ease-out">

<!-- Modal backdrop (emphasized) -->
<div class="transition-opacity duration-300 ease-in-out">
```

## Custom Animations

Defined in [`app.css`](../src/app.css:147):

### Available Animations

```css
/* Pulsing glow effect */
.animate-pulse-glow
/* Usage: Status indicators, "thinking" states */

/* Typing indicator dots */
.animate-typing-dot
/* Usage: Assistant thinking animation */

/* Slide in from bottom */
.animate-slide-in-up
/* Usage: New message cards, notifications */

/* Shimmer loading effect */
.animate-shimmer
/* Usage: Skeleton loaders, placeholders */

/* Breathing effect */
.animate-breathe
/* Usage: Subtle status indicators */

/* Fade in */
.animate-fade-in
/* Usage: Content reveals */

/* Subtle bounce */
.animate-bounce-subtle
/* Usage: Attention-grabbing elements */
```

### Animation Examples

```svelte
<!-- Thinking indicator -->
<div class="flex gap-1">
  <span class="size-1 rounded-full bg-current animate-typing-dot" />
  <span class="size-1 rounded-full bg-current animate-typing-dot" style="animation-delay: 0.2s" />
  <span class="size-1 rounded-full bg-current animate-typing-dot" style="animation-delay: 0.4s" />
</div>

<!-- Skeleton loader -->
<div class="h-20 w-full rounded-md animate-shimmer" />

<!-- Status badge -->
<Badge class="animate-pulse-glow">Active</Badge>

<!-- New message -->
<MessageCard class="animate-slide-in-up" />
```

## Shadows

### Elevation Levels

```svelte
<!-- No shadow -->
<div class="shadow-none">

<!-- Subtle shadow -->
<div class="shadow-sm">  <!-- 0 1px 2px 0 rgba(0, 0, 0, 0.05) -->

<!-- Default shadow -->
<div class="shadow">     <!-- 0 1px 3px 0 rgba(0, 0, 0, 0.1) -->

<!-- Medium shadow -->
<div class="shadow-md">  <!-- 0 4px 6px -1px rgba(0, 0, 0, 0.1) -->

<!-- Large shadow -->
<div class="shadow-lg">  <!-- 0 10px 15px -3px rgba(0, 0, 0, 0.1) -->

<!-- Extra large shadow -->
<div class="shadow-xl">  <!-- 0 20px 25px -5px rgba(0, 0, 0, 0.1) -->
```

### Usage Guidelines

- Cards at rest: `shadow` or `shadow-sm`
- Cards on hover: `shadow-md` or `shadow-lg`
- Modals and dialogs: `shadow-xl`
- Popovers and tooltips: `shadow-lg`

## Z-Index Layers

```css
/* Layering order (use Tailwind utilities) */
z-0    /* Base layer */
z-10   /* Raised elements (cards on hover) */
z-20   /* Dropdown menus */
z-30   /* Fixed headers, status bars */
z-40   /* Modals, sheets */
z-50   /* Tooltips, popovers */
```

## Accessibility Considerations

### Contrast Ratios

All color combinations meet WCAG 2.1 AA standards:

- Normal text: 4.5:1 minimum
- Large text (18pt+): 3:1 minimum
- UI components: 3:1 minimum

### Focus Indicators

```svelte
<!-- All focusable elements should use -->
<button class="focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
```

### Motion Preferences

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

## Component-Specific Tokens

### Badges

```svelte
<!-- Default badge -->
<Badge variant="default" class="bg-primary text-primary-foreground">

<!-- Secondary badge -->
<Badge variant="secondary" class="bg-secondary text-secondary-foreground">

<!-- Outline badge -->
<Badge variant="outline" class="border border-border">

<!-- Destructive badge -->
<Badge variant="destructive" class="bg-destructive">
```

### Buttons

```svelte
<!-- Primary button -->
<Button variant="default" class="bg-primary text-primary-foreground hover:bg-primary/90">

<!-- Secondary button -->
<Button variant="secondary" class="bg-secondary text-secondary-foreground hover:bg-secondary/80">

<!-- Ghost button -->
<Button variant="ghost" class="hover:bg-accent hover:text-accent-foreground">

<!-- Outline button -->
<Button variant="outline" class="border border-input hover:bg-accent">
```

### Cards

```svelte
<!-- Standard card -->
<Card.Root class="bg-card text-card-foreground border border-border">
  <Card.Header class="p-6">
  <Card.Content class="p-6 pt-0">
</Card.Root>

<!-- Elevated card (on hover) -->
<Card.Root class="transition-shadow duration-150 hover:shadow-lg">
```

## References

- Tailwind CSS v4: https://tailwindcss.com/
- shadcn-svelte: https://shadcn-svelte.com/
- OKLCH Color Space: https://oklch.com/
- WCAG 2.1 Guidelines: https://www.w3.org/WAI/WCAG21/quickref/

## Component Configuration

See [`components.json`](../components.json:1) for shadcn-svelte configuration.
See [`app.css`](../src/app.css:1) for theme implementation.
