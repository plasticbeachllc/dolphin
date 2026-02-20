<script lang="ts">
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { MessageCard } from "$lib/components/chat";
  import { ToolCallCard, DiffViewer } from "$lib/components/tools";
  import { Loader2 } from "lucide-svelte";

  interface Message {
    type?: "tool_call" | "thinking";
    role?: "user" | "assistant";
    content?: string;
    timestamp?: string;
    tool?: string;
    input?: Record<string, unknown>;
    result?: unknown;
    error?: unknown;
    status?: "running" | "success" | "error";
    executionTime?: number;
    diff?: any;
  }

  interface Props {
    messages: Message[];
    autoScroll?: boolean;
  }

  let { messages, autoScroll = true }: Props = $props();
  let messagesEndRef = $state<HTMLDivElement>();

  const FILE_EDIT_TOOLS = ['apply_diff', 'write_to_file', 'file_write', 'search_and_replace', 'insert_content'];

  console.log(`[MessageList] Rendering with ${messages.length} messages`);

  $effect(() => {
    // Only trigger on messages length change, not on array reference change
    const msgCount = messages.length;

    // Add a guard to prevent infinite loops during initial render
    if (msgCount === 0) {
      return;
    }

    console.log(`[MessageList] Effect triggered - message count: ${msgCount}`);

    if (autoScroll && messagesEndRef) {
      messagesEndRef.scrollIntoView({ behavior: "smooth" });
    }
  });
</script>

<ScrollArea class="h-full w-full" role="log" aria-label="Chat messages" aria-live="polite">
  <div class="p-2 space-y-2">
    {#each messages as message, i (i)}
      {#if message.type === "tool_call"}
        {#if message.status === 'success' && FILE_EDIT_TOOLS.includes(message.tool!) && message.diff}
          <div class="mb-2">
            <DiffViewer diff={message.diff} defaultExpanded={true} />
          </div>
        {:else}
          <ToolCallCard
            tool={message.tool!}
            input={message.input!}
            result={message.result}
            error={message.error}
            status={message.status || "running"}
            executionTime={message.executionTime}
            diff={message.diff}
          />
        {/if}
      {:else if message.type === "thinking"}
        <!-- Thinking indicator -->
        <div class="flex items-center gap-3 text-muted-foreground py-2 px-3" role="status" aria-live="polite" aria-label="AI is thinking">
          <Loader2 class="h-4 w-4 animate-spin" aria-hidden="true" />
          <span class="text-sm">Thinking...</span>
        </div>
      {:else}
        <MessageCard
          role={message.role!}
          content={message.content!}
          timestamp={message.timestamp}
        />
      {/if}
    {/each}
    <div bind:this={messagesEndRef} aria-hidden="true"></div>
  </div>
</ScrollArea>
