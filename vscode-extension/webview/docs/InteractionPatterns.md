# Interaction Patterns

This document defines standard interaction patterns for the Dolphin UI, ensuring consistency and predictability across all components.

## Core Principles

1. **Instant Feedback**: Every user action should have immediate visual feedback
2. **Progressive Disclosure**: Show details on demand, keep interfaces clean by default
3. **Clear Affordances**: Make interactive elements obviously interactive
4. **Accessible by Default**: All patterns work with keyboard, mouse, and screen readers

## Hover States

### Standard Hover Pattern

All interactive elements should provide visual feedback on hover:

```svelte
<!-- Button hover -->
<Button class="hover:bg-accent hover:text-accent-foreground transition-colors duration-100">

<!-- Card hover -->
<Card.Root class="hover:shadow-md hover:border-primary transition-all duration-150 cursor-pointer">

<!-- Link hover -->
<a class="hover:underline hover:text-primary transition-colors duration-100">

<!-- Icon button hover -->
<button class="hover:bg-accent/50 rounded-md p-2 transition-colors duration-100">
```

### Hover with Scale

For emphasis on interactive cards or tiles:

```svelte
<div class="transition-transform duration-150 hover:scale-105 cursor-pointer">
  <Card.Root>
    <!-- Content -->
  </Card.Root>
</div>
```

### Hover with Elevation

Cards that "lift" on hover:

```svelte
<Card.Root class="transition-all duration-200 hover:shadow-lg hover:-translate-y-1">
  <!-- Content -->
</Card.Root>
```

### Disabled Hover

```svelte
<Button
  disabled
  class="disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-primary"
>
  Can't click me
</Button>
```

## Focus States

### Focus Ring Pattern (Keyboard Navigation)

All focusable elements must have visible focus indicators:

```svelte
<!-- Standard focus ring -->
<button class="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">

<!-- Focus with accent color -->
<input class="focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2">

<!-- Focus without offset (for compact UIs) -->
<button class="focus-visible:ring-2 focus-visible:ring-ring">
```

### Focus Management in Modals

When opening a modal or sheet, focus should:

1. Move to the first focusable element inside
2. Trap focus within the modal (no tabbing outside)
3. Return to the trigger element on close

```svelte
<script>
  import * as Dialog from "$lib/components/ui/dialog";

  // shadcn-svelte Dialog handles this automatically
</script>

<Dialog.Root>
  <Dialog.Trigger>Open</Dialog.Trigger>
  <Dialog.Content>
    <!-- Focus automatically moves here -->
    <Dialog.Header>
      <Dialog.Title>Modal Title</Dialog.Title>
    </Dialog.Header>
    <!-- Tab navigation trapped within -->
  </Dialog.Content>
</Dialog.Root>
```

## Active/Pressed States

### Button Press Effect

```svelte
<!-- Scale down on press -->
<Button class="active:scale-95 transition-transform duration-75">
  Click me
</Button>

<!-- Darken on press -->
<Button class="active:brightness-90 transition-all duration-75">
  Click me
</Button>
```

### Card Selection

```svelte
<script>
  let selected = $state(false);
</script>

<Card.Root
  class="cursor-pointer transition-all duration-150 border-2"
  class:border-primary={selected}
  class:border-border={!selected}
  class:shadow-md={selected}
  onclick={() => selected = !selected}
>
  <!-- Content -->
</Card.Root>
```

## Loading States

### Spinner/Pulse

```svelte
<!-- Pulse animation for "thinking" -->
<Badge variant="secondary" class="flex items-center gap-2">
  <span>Loading</span>
  <div class="flex gap-0.5">
    <span class="size-1 rounded-full bg-current animate-pulse" />
    <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 150ms" />
    <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 300ms" />
  </div>
</Badge>
```

### Skeleton Loaders

```svelte
<script>
  import { Skeleton } from "$lib/components/ui/skeleton";
</script>

<!-- Card skeleton -->
<Card.Root>
  <Card.Header>
    <Skeleton class="h-4 w-[250px]" />
    <Skeleton class="h-4 w-[200px]" />
  </Card.Header>
  <Card.Content>
    <Skeleton class="h-[125px] w-full" />
  </Card.Content>
</Card.Root>

<!-- Text skeleton -->
<div class="space-y-2">
  <Skeleton class="h-4 w-full" />
  <Skeleton class="h-4 w-[80%]" />
  <Skeleton class="h-4 w-[60%]" />
</div>
```

### Progress Indicators

```svelte
<script>
  import { Progress } from "$lib/components/ui/progress";

  let progress = $state(45);
</script>

<!-- Determinate progress -->
<Progress value={progress} max={100} class="w-full" />

<!-- Indeterminate progress -->
<Progress value={undefined} class="w-full" />
```

### Shimmer Effect

```svelte
<!-- Shimmer loading for images or large content blocks -->
<div class="h-48 w-full rounded-md animate-shimmer" />
```

## Disabled States

### Visual Indicators

```svelte
<!-- Disabled button -->
<Button
  disabled
  class="disabled:opacity-50 disabled:cursor-not-allowed"
>
  Disabled
</Button>

<!-- Disabled input -->
<Input
  disabled
  class="disabled:opacity-60 disabled:cursor-not-allowed disabled:bg-muted"
/>

<!-- Disabled card -->
<Card.Root class="opacity-60 pointer-events-none">
  <!-- Content -->
</Card.Root>
```

### Screen Reader Support

```svelte
<Button disabled aria-disabled="true" aria-label="Submit button, currently disabled">
  Submit
</Button>
```

## Micro-Interactions

### Checkbox Toggle

```svelte
<script>
  import { Checkbox } from "$lib/components/ui/checkbox";
</script>

<!-- Animated checkbox with label -->
<div class="flex items-center gap-2">
  <Checkbox
    id="agree"
    class="transition-all duration-150 data-[state=checked]:scale-110"
  />
  <label for="agree" class="text-sm cursor-pointer select-none">
    I agree to the terms
  </label>
</div>
```

### Badge Pulse (Live Updates)

```svelte
<!-- Pulse when data is updating -->
<Badge
  variant="default"
  class="transition-all"
  class:animate-pulse={isUpdating}
>
  {count} updates
</Badge>
```

### Icon Rotation

```svelte
<script>
  import { ChevronDown } from "lucide-svelte";
  let isOpen = $state(false);
</script>

<button
  onclick={() => isOpen = !isOpen}
  class="flex items-center gap-2"
>
  <span>Details</span>
  <ChevronDown
    class="size-4 transition-transform duration-200"
    class:rotate-180={isOpen}
  />
</button>
```

### Button Icon Swap

```svelte
<script>
  import { Play, Pause } from "lucide-svelte";
  let isPlaying = $state(false);
</script>

<Button onclick={() => isPlaying = !isPlaying}>
  {#if isPlaying}
    <Pause class="size-4 mr-2" />
    Pause
  {:else}
    <Play class="size-4 mr-2" />
    Play
  {/if}
</Button>
```

## Tooltip Pattern

### Standard Tooltip

```svelte
<script>
  import * as Tooltip from "$lib/components/ui/tooltip";
</script>

<Tooltip.Root>
  <Tooltip.Trigger asChild>
    <Button variant="ghost" size="icon">
      <Info class="size-4" />
    </Button>
  </Tooltip.Trigger>
  <Tooltip.Content>
    <p>Additional information</p>
  </Tooltip.Content>
</Tooltip.Root>
```

### Tooltip Delay

```svelte
<!-- Delay tooltip appearance to reduce noise -->
<Tooltip.Root delayDuration={500}>
  <Tooltip.Trigger>Hover me</Tooltip.Trigger>
  <Tooltip.Content>Delayed tooltip</Tooltip.Content>
</Tooltip.Root>
```

### Rich Tooltip

```svelte
<Tooltip.Root>
  <Tooltip.Trigger>Complex info</Tooltip.Trigger>
  <Tooltip.Content class="max-w-xs">
    <div class="space-y-2">
      <p class="font-semibold">Detailed Information</p>
      <p class="text-xs text-muted-foreground">
        This provides extended context that wouldn't fit in a simple tooltip.
      </p>
    </div>
  </Tooltip.Content>
</Tooltip.Root>
```

## Popover Pattern

### Standard Popover

```svelte
<script>
  import * as Popover from "$lib/components/ui/popover";
</script>

<Popover.Root>
  <Popover.Trigger asChild>
    <Button variant="outline">Open</Button>
  </Popover.Trigger>
  <Popover.Content class="w-80">
    <div class="space-y-2">
      <h4 class="font-medium">Popover Title</h4>
      <p class="text-sm text-muted-foreground">
        Detailed content goes here.
      </p>
    </div>
  </Popover.Content>
</Popover.Root>
```

### Popover vs Tooltip

- **Tooltip**: Short, descriptive text (1-2 sentences). Auto-closes on unhover.
- **Popover**: Rich content, forms, or actions. Requires click to close.

## Accordion Pattern

### Collapsible Sections

```svelte
<script>
  import * as Accordion from "$lib/components/ui/accordion";
</script>

<!-- Single item open at a time -->
<Accordion.Root type="single" collapsible>
  <Accordion.Item value="item-1">
    <Accordion.Trigger>Section 1</Accordion.Trigger>
    <Accordion.Content>
      Content for section 1
    </Accordion.Content>
  </Accordion.Item>
  <Accordion.Item value="item-2">
    <Accordion.Trigger>Section 2</Accordion.Trigger>
    <Accordion.Content>
      Content for section 2
    </Accordion.Content>
  </Accordion.Item>
</Accordion.Root>

<!-- Multiple items can be open -->
<Accordion.Root type="multiple">
  <!-- Items -->
</Accordion.Root>
```

### Accordion with Icons

```svelte
<Accordion.Item value="details">
  <Accordion.Trigger class="hover:no-underline">
    <div class="flex items-center gap-2">
      <FileText class="size-4" />
      <span>File Details</span>
    </div>
  </Accordion.Trigger>
  <Accordion.Content>
    <!-- Details -->
  </Accordion.Content>
</Accordion.Item>
```

## Tab Pattern

### Standard Tabs

```svelte
<script>
  import * as Tabs from "$lib/components/ui/tabs";
</script>

<Tabs.Root value="tab1">
  <Tabs.List>
    <Tabs.Trigger value="tab1">Overview</Tabs.Trigger>
    <Tabs.Trigger value="tab2">Details</Tabs.Trigger>
    <Tabs.Trigger value="tab3">Settings</Tabs.Trigger>
  </Tabs.List>

  <Tabs.Content value="tab1">
    Overview content
  </Tabs.Content>
  <Tabs.Content value="tab2">
    Details content
  </Tabs.Content>
  <Tabs.Content value="tab3">
    Settings content
  </Tabs.Content>
</Tabs.Root>
```

### Tabs with Badges

```svelte
<Tabs.Trigger value="notifications">
  <span class="flex items-center gap-2">
    Notifications
    <Badge variant="secondary" class="ml-1">5</Badge>
  </span>
</Tabs.Trigger>
```

## Drag and Drop (Future)

### Visual Feedback

```svelte
<!-- Drop zone -->
<div
  class="border-2 border-dashed border-border rounded-lg p-8 transition-colors"
  class:border-primary={isDragOver}
  class:bg-accent/50={isDragOver}
>
  Drop files here
</div>

<!-- Draggable item -->
<div
  draggable="true"
  class="cursor-move transition-opacity"
  class:opacity-50={isDragging}
>
  Drag me
</div>
```

## Command Palette Pattern

### Keyboard-First Navigation

```svelte
<script>
  import * as Command from "$lib/components/ui/command";
</script>

<!-- Trigger with Cmd+K / Ctrl+K -->
<Command.Root>
  <Command.Input placeholder="Type a command or search..." />
  <Command.List>
    <Command.Empty>No results found.</Command.Empty>
    <Command.Group heading="Suggestions">
      <Command.Item onSelect={handleSelect}>
        <File class="mr-2 size-4" />
        <span>Open file</span>
        <Command.Shortcut>⌘O</Command.Shortcut>
      </Command.Item>
      <Command.Item>
        <Search class="mr-2 size-4" />
        <span>Search</span>
        <Command.Shortcut>⌘F</Command.Shortcut>
      </Command.Item>
    </Command.Group>
  </Command.List>
</Command.Root>
```

## Context Menu Pattern

### Right-Click Actions

```svelte
<script>
  import * as ContextMenu from "$lib/components/ui/context-menu";
</script>

<ContextMenu.Root>
  <ContextMenu.Trigger>
    <Card.Root>Right-click me</Card.Root>
  </ContextMenu.Trigger>
  <ContextMenu.Content>
    <ContextMenu.Item>
      <Copy class="mr-2 size-4" />
      Copy
    </ContextMenu.Item>
    <ContextMenu.Item>
      <Edit class="mr-2 size-4" />
      Edit
    </ContextMenu.Item>
    <ContextMenu.Separator />
    <ContextMenu.Item class="text-destructive">
      <Trash class="mr-2 size-4" />
      Delete
    </ContextMenu.Item>
  </ContextMenu.Content>
</ContextMenu.Root>
```

## Sheet/Drawer Pattern

### Side Panel

```svelte
<script>
  import * as Sheet from "$lib/components/ui/sheet";
</script>

<!-- Slide from right -->
<Sheet.Root>
  <Sheet.Trigger asChild>
    <Button>Open Details</Button>
  </Sheet.Trigger>
  <Sheet.Content side="right" class="w-[400px] sm:w-[540px]">
    <Sheet.Header>
      <Sheet.Title>Details</Sheet.Title>
      <Sheet.Description>
        Additional context and actions
      </Sheet.Description>
    </Sheet.Header>
    <!-- Content -->
  </Sheet.Content>
</Sheet.Root>
```

## Error States

### Inline Errors

```svelte
<script>
  let error = $state("Invalid email address");
</script>

<div class="space-y-2">
  <Input
    type="email"
    class="border-destructive focus-visible:ring-destructive"
    aria-invalid="true"
    aria-describedby="email-error"
  />
  {#if error}
    <p id="email-error" class="text-xs text-destructive flex items-center gap-1">
      <AlertCircle class="size-3" />
      {error}
    </p>
  {/if}
</div>
```

### Toast Notifications

```svelte
<script>
  import { toast } from "svelte-sonner";
</script>

<!-- Success toast -->
<Button onclick={() => toast.success("Saved successfully!")}>
  Save
</Button>

<!-- Error toast -->
<Button onclick={() => toast.error("Failed to save", {
  description: "Please try again later"
})}>
  Delete
</Button>

<!-- Promise toast -->
<Button onclick={() => toast.promise(
  saveData(),
  {
    loading: "Saving...",
    success: "Data saved!",
    error: "Failed to save"
  }
)}>
  Save with feedback
</Button>
```

## Animation Sequences

### Staggered Reveals

```svelte
<!-- Progressive reveal of list items -->
{#each items as item, i}
  <div
    class="animate-slide-in-up"
    style="animation-delay: {i * 50}ms"
  >
    <Card.Root>
      {item.content}
    </Card.Root>
  </div>
{/each}
```

### Entrance Animations

```svelte
<!-- Fade and slide in -->
<div class="animate-fade-in">
  <Card.Root>Content</Card.Root>
</div>

<!-- Scale up -->
<div class="animate-in zoom-in-95 duration-200">
  <Badge>New</Badge>
</div>
```

## Accessibility Checklist

For every interactive pattern:

- [ ] **Keyboard navigable**: Can be accessed via Tab, Enter, Space, Arrow keys
- [ ] **Focus visible**: Clear focus indicator (`focus-visible:ring-2`)
- [ ] **ARIA labels**: Descriptive `aria-label` or `aria-labelledby`
- [ ] **Live regions**: Use `aria-live` for dynamic content updates
- [ ] **Screen reader friendly**: Test with NVDA/VoiceOver
- [ ] **Role attributes**: Proper semantic roles (`role="button"`, etc.)
- [ ] **State communication**: `aria-expanded`, `aria-selected`, `aria-checked`

## Common Patterns Summary

| Pattern         | Component                | Usage                                              |
| --------------- | ------------------------ | -------------------------------------------------- |
| Hover feedback  | All interactive elements | `hover:bg-accent transition-colors duration-100`   |
| Focus indicator | All focusable elements   | `focus-visible:ring-2 focus-visible:ring-ring`     |
| Active state    | Buttons, cards           | `active:scale-95 transition-transform duration-75` |
| Disabled state  | Forms, buttons           | `disabled:opacity-50 disabled:cursor-not-allowed`  |
| Loading state   | Cards, lists             | Use `Skeleton` component or `animate-pulse`        |
| Tooltip         | Icons, abbreviations     | `Tooltip` component with `delayDuration={500}`     |
| Popover         | Rich content             | `Popover` component for clickable content          |
| Modal           | Important actions        | `Dialog` component with focus management           |
| Side panel      | Details view             | `Sheet` component, slide from right                |

## References

- [shadcn-svelte Components](https://shadcn-svelte.com/docs/components)
- [Bits UI Accessibility](https://bits-ui.com/docs/accessibility)
- [WCAG 2.1 Interactive Patterns](https://www.w3.org/WAI/WCAG21/quickref/)
- [Design Tokens](./DesignTokens.md)
