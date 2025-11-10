<script lang="ts">
  import { Textarea } from "$lib/components/ui/textarea";
  import { Button } from "$lib/components/ui/button";
  import { SendHorizontal, Square, Plus } from "lucide-svelte";

  interface Props {
    onSend?: (message: string) => void;
    onStop?: () => void;
    placeholder?: string;
    disabled?: boolean;
    isProcessing?: boolean;
    hasActiveConversation?: boolean;
  }

  let {
    onSend,
    onStop,
    placeholder = "Type a message...",
    disabled = false,
    isProcessing = false,
    hasActiveConversation = false
  }: Props = $props();

  let message = $state("");
  let textareaRef: HTMLTextAreaElement | null = $state(null);
  
  // Determine if we should show "New Conversation" button
  let showNewConversationButton = $derived(!hasActiveConversation && !message.trim());

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

  // Export a prefill method that can be called by parent
  export function prefill(text: string) {
    message = text;
    textareaRef?.focus();
  }
</script>

<div class="input-wrapper" role="region" aria-label="Message input">
  <Textarea
    bind:ref={textareaRef}
    bind:value={message}
    {placeholder}
    disabled={disabled || isProcessing}
    onkeydown={handleKeyDown}
    rows={3}
    class="flex-1 min-h-[4.5rem] max-h-48 resize-none"
    aria-label="Type your message here. Press Ctrl+Enter or Cmd+Enter to send."
    aria-describedby={isProcessing ? "processing-status" : undefined}
  />
  {#if isProcessing}
    <span id="processing-status" class="sr-only" aria-live="polite">Processing your message</span>
  {/if}
  <Button
    onclick={handleAction}
    disabled={disabled && !isProcessing}
    variant={isProcessing ? "destructive" : "default"}
    size="icon"
    class="shrink-0 self-end"
    aria-label={isProcessing ? "Stop generation" : showNewConversationButton ? "Start new conversation" : "Send message"}
    title={isProcessing ? "Stop (Ctrl+Enter)" : "Send (Ctrl+Enter)"}
  >
    {#if isProcessing}
      <Square class="h-4 w-4" aria-hidden="true" />
    {:else if showNewConversationButton}
      <Plus class="h-4 w-4" aria-hidden="true" />
    {:else}
      <SendHorizontal class="h-4 w-4" aria-hidden="true" />
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

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
  }
</style>