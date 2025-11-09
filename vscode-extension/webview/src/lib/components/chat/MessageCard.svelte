<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import * as Avatar from "$lib/components/ui/avatar";
  import { Badge } from "$lib/components/ui/badge";
  
  interface Props {
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
  }
  
  let { role, content, timestamp }: Props = $props();
  
  const isUser = role === "user";
  const avatarFallback = isUser ? "U" : "A";
</script>

<Card.Root class="mb-4 {isUser ? 'ml-auto' : 'mr-auto'} max-w-[85%]">
  <Card.Header class="flex flex-row items-center gap-3 pb-3">
    <Avatar.Root class="h-8 w-8">
      <Avatar.Fallback class={isUser ? "bg-blue-500" : "bg-purple-500"}>
        {avatarFallback}
      </Avatar.Fallback>
    </Avatar.Root>
    <div class="flex flex-1 items-center justify-between">
      <Badge variant={isUser ? "secondary" : "default"}>
        {isUser ? "You" : "Assistant"}
      </Badge>
      {#if timestamp}
        <span class="text-xs text-muted-foreground">{timestamp}</span>
      {/if}
    </div>
  </Card.Header>
  <Card.Content class="whitespace-pre-wrap break-words">
    {content}
  </Card.Content>
</Card.Root>