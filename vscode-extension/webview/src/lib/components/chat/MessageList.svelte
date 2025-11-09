<script lang="ts">
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { MessageCard } from "$lib/components/chat";
  
  interface Message {
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
  }
  
  interface Props {
    messages: Message[];
    autoScroll?: boolean;
  }
  
  let { messages, autoScroll = true }: Props = $props();
  let messagesEndRef = $state<HTMLDivElement>();
  
  $effect(() => {
    if (autoScroll && messagesEndRef) {
      messagesEndRef.scrollIntoView({ behavior: "smooth" });
    }
  });
</script>

<ScrollArea class="flex-1">
  <div class="p-4 space-y-4">
    {#each messages as message (message.timestamp || message.content)}
      <MessageCard
        role={message.role}
        content={message.content}
        timestamp={message.timestamp}
      />
    {/each}
    <div bind:this={messagesEndRef}></div>
  </div>
</ScrollArea>