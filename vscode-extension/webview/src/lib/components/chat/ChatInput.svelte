<script lang="ts">
  import { Textarea } from "$lib/components/ui/textarea";
  import { Button } from "$lib/components/ui/button";
  import { SendHorizontal, Square } from "lucide-svelte";

  interface Props {
    onSend?: (message: string) => void;
    onStop?: () => void;
    placeholder?: string;
    disabled?: boolean;
    isProcessing?: boolean;
  }

  let {
    onSend,
    onStop,
    placeholder = "Type a message...",
    disabled = false,
    isProcessing = false
  }: Props = $props();

  let message = $state("");
  let textareaRef: HTMLTextAreaElement | null = $state(null);

  function handleKeyDown(event: KeyboardEvent) {
    // Cmd+Enter (Mac) or Ctrl+Enter (Windows/Linux) to send
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      handleAction();
    }
  }

  function handleAction() {
    if (isProcessing) {
      // Stop current operation
      onStop?.();
    } else {
      // Send message
      if (!message.trim() || disabled) return;
      onSend?.(message);
      message = "";
    }
  }

  // Export a focus method that can be called by parent
  export function focus() {
    textareaRef?.focus();
  }
</script>

<div class="input-wrapper">
  <Textarea
    bind:ref={textareaRef}
    bind:value={message}
    {placeholder}
    disabled={disabled || isProcessing}
    onkeydown={handleKeyDown}
    rows={3}
    class="flex-1 min-h-[4.5rem] max-h-48 resize-none"
  />
  <Button
    onclick={handleAction}
    disabled={disabled && !isProcessing}
    variant={isProcessing ? "destructive" : "default"}
    size="icon"
    class="shrink-0 self-end"
    aria-label={isProcessing ? "Stop" : "Send"}
  >
    {#if isProcessing}
      <Square class="h-4 w-4" />
    {:else}
      <SendHorizontal class="h-4 w-4" />
    {/if}
  </Button>
</div>

<style>
  .input-wrapper {
    display: flex;
    gap: 0.75rem;
    width: 100%;
    align-items: flex-end;
  }
</style>