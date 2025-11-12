
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  
  onMount(() => {
    goto('/gallery', { replaceState: true });
  });
</script>

<div class="flex items-center justify-center h-screen">
  <div class="text-center">
    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
    <p class="text-muted-foreground">Redirecting to gallery...</p>
  </div>
</div>
