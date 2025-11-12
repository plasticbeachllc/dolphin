<script lang="ts">
  import { Button } from '$lib/components/ui/button';
  import { AlertTriangle } from 'lucide-svelte';
  import { onMount } from 'svelte';

  interface Props {
    title?: string;
    message?: string;
    options?: string[];
    onSelect: (choice: string) => void;
  }

  let {
    title = 'Confirm',
    message = '',
    options = ['Allow Once', 'Always Allow', 'Deny'],
    onSelect
  }: Props = $props();

  let dialogRef: HTMLDivElement;
  let firstButton: HTMLElement;
  let previouslyFocusedElement: HTMLElement | null = null;

  onMount(() => {
    // Save currently focused element
    previouslyFocusedElement = document.activeElement as HTMLElement;

    // Focus first button
    setTimeout(() => {
      firstButton?.focus();
    }, 0);

    // Cleanup: restore focus when dialog is removed
    return () => {
      previouslyFocusedElement?.focus();
    };
  });

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      onSelect(options[options.length - 1] || 'Deny'); // Default to last option (usually Deny)
    }

    // Focus trap
    if (event.key === 'Tab') {
      const focusableElements = dialogRef.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      const firstFocusable = focusableElements[0] as HTMLElement;
      const lastFocusable = focusableElements[focusableElements.length - 1] as HTMLElement;

      if (event.shiftKey && document.activeElement === firstFocusable) {
        event.preventDefault();
        lastFocusable.focus();
      } else if (!event.shiftKey && document.activeElement === lastFocusable) {
        event.preventDefault();
        firstFocusable.focus();
      }
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
  <div
    bind:this={dialogRef}
    role="dialog"
    aria-modal="true"
    aria-labelledby="dialog-title"
    aria-describedby="dialog-description"
    class="bg-background border border-border rounded-lg p-4 w-[400px] shadow-lg"
  >
    <div class="flex items-start gap-3 mb-4">
      <AlertTriangle class="h-5 w-5 text-orange-500 mt-0.5" aria-hidden="true" />
      <div class="flex-1">
        <h3 id="dialog-title" class="font-semibold mb-2">{title}</h3>
        <p id="dialog-description" class="text-sm text-muted-foreground">{message}</p>
      </div>
    </div>

    <div class="flex gap-2 justify-end">
      {#each options as opt, index}
        <Button
          bind:ref={(el) => {
            if (index === 0) {
              firstButton = el;
            }
          }}
          size="sm"
          variant={opt.toLowerCase().includes('deny') ? 'destructive' : 'default'}
          onclick={() => onSelect(opt)}
        >
          {opt}
        </Button>
      {/each}
    </div>
  </div>
</div>

<style>
  /* Prevent scrolling when dialog is open */
  :global(body:has(.fixed)) {
    overflow: hidden;
  }
</style>