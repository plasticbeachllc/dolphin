
<script lang="ts">
  import { MessageList, ChatInput } from '$lib/components/chat';
  
  let messages = $state([
    { role: "user", content: "Hello, can you help me?", timestamp: "2:30 PM" },
    { role: "assistant", content: "<p>Of course! I'd be happy to help.</p>", timestamp: "2:30 PM" }
  ]);
  
  function handleSend(message: string) {
    messages = [...messages, {
      role: "user",
      content: message,
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    }];
    
    // Simulate assistant response
    setTimeout(() => {
      messages = [...messages, {
        role: "assistant",
        content: `<p>You said: "${message}"</p>`,
        timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
      }];
    }, 500);
  }
</script>

<div class="flex h-screen flex-col">
  <MessageList {messages} />
  <ChatInput onSend={handleSend} />
</div>
