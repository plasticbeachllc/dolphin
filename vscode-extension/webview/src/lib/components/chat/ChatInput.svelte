<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";
  import { Button } from "$lib/components/ui/button";
  
  interface Props {
    onSend?: (message: string) => void;
    placeholder?: string;
    disabled?: boolean;
  }
  
  let { onSend, placeholder = "Type a message...", disabled = false }: Props = $props();
  
  let message = $state("");
  
  function handleKeyDown(event: KeyboardEvent) {
    // Cmd+Enter (Mac) or Ctrl+Enter (Windows/Linux)
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      handleSend();
    }
  }
  
  function handleSend() {
    if (!message.trim() || disabled) return;
    
    onSend?.(message);
    message = "";
  }
</script>

<Card.Root class="sticky bottom-0 border-t">
  <Card.Content class="flex gap-2 p-4">
    <Input
      type="text"
      bind:value={message}
      {placeholder}
      {disabled}
      onkeydown={handleKeyDown}
      class="flex-1"
    />
    <Button 
      onclick={handleSend} 
      {disabled}
      class="shrink-0"
    >
      Send
    </Button>
  </Card.Content>
</Card.Root>