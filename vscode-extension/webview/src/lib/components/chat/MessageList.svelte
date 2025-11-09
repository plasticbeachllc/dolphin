<script lang="ts">
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { MessageCard } from "$lib/components/chat";
  import { ToolCallCard } from "$lib/components/tools";
  
  interface Message {
    type?: "tool_call";
    role?: "user" | "assistant";
    content?: string;
    timestamp?: string;
    tool?: string;
    input?: Record<string, any>;
    result?: Record<string, any>;
    error?: string;
    status?: "running" | "success" | "error";
    executionTime?: number;
  }
  
  interface Props {
    messages: Message[];
    autoScroll?: boolean;
  }
  
  let { messages, autoScroll = true }: Props = $props();
  let messagesEndRef = $state<HTMLDivElement>();
  
  $effect(() => {
    // Trigger on messages length change
    messages.length;
    
    if (autoScroll && messagesEndRef) {
      messagesEndRef.scrollIntoView({ behavior: "smooth" });
    }
  });
</script>

<ScrollArea class="h-full w-full">
  <div class="p-2 space-y-2">
    {#each messages as message, i (i)}
      {#if message.type === "tool_call"}
        <ToolCallCard
          tool={message.tool!}
          input={message.input!}
          result={message.result}
          error={message.error}
          status={message.status || "running"}
          executionTime={message.executionTime}
        />
      {:else}
        <MessageCard
          role={message.role!}
          content={message.content!}
          timestamp={message.timestamp}
        />
      {/if}
    {/each}
    <div bind:this={messagesEndRef}></div>
  </div>
</ScrollArea>