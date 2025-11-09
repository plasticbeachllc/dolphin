<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";
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
  
  function handleKeyDown(event: KeyboardEvent) {
    // Cmd+Enter (Mac) or Ctrl+Enter (Windows/Linux)
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
</script>

<Card.Root class="sticky bottom-0 border-t">
  <Card.Content class="flex gap-2 p-4">
    <Input
      type="text"
      bind:value={message}
      {placeholder}
      disabled={disabled || isProcessing}
      onkeydown={handleKeyDown}
      class="flex-1"
    />
    <Button
      onclick={handleAction}
      disabled={disabled && !isProcessing}
      variant={isProcessing ? "destructive" : "default"}
      size="icon"
      class="shrink-0"
      aria-label={isProcessing ? "Stop" : "Send"}
    >
      {#if isProcessing}
        <Square class="h-4 w-4" />
      {:else}
        <SendHorizontal class="h-4 w-4" />
      {/if}
    </Button>
  </Card.Content>
</Card.Root>