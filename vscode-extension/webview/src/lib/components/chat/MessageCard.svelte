<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import * as Avatar from "$lib/components/ui/avatar";
  import { Badge } from "$lib/components/ui/badge";
  import MarkdownContent from "./MarkdownContent.svelte";
  
  interface Props {
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
  }
  
  let { role, content, timestamp }: Props = $props();
  
  const isUser = role === "user";
  const avatarFallback = isUser ? "U" : "A";
</script>

<Card.Root
  class="mb-2 {isUser ? 'ml-auto' : 'mr-auto'} max-w-[96%] rounded-md"
  role="article"
  aria-label="{isUser ? 'User' : 'Assistant'} message{timestamp ? ' at ' + timestamp : ''}"
>
  <Card.Header class="flex flex-row items-center gap-2 pb-1 px-3 pt-2">
    <Avatar.Root class="h-8 w-8" aria-hidden="true">
      <Avatar.Fallback class={isUser ? "bg-primary" : "bg-accent"}>
        {avatarFallback}
      </Avatar.Fallback>
    </Avatar.Root>
    <div class="flex flex-1 items-center justify-between">
      <Badge variant={isUser ? "secondary" : "default"} aria-label="Message from {isUser ? 'You' : 'Assistant'}">
        {isUser ? "You" : "Assistant"}
      </Badge>
      {#if timestamp}
        <span class="text-xs text-muted-foreground" aria-label="Sent at {timestamp}">
          {timestamp}
        </span>
      {/if}
    </div>
  </Card.Header>
  <Card.Content class="prose prose-sm max-w-none dark:prose-invert px-3 pb-2 pt-0">
    {#if isUser}
      <div class="whitespace-pre-wrap break-words text-sm">
        {content}
      </div>
    {:else}
      <MarkdownContent content={content} />
    {/if}
  </Card.Content>
</Card.Root>