<script lang="ts">
  import { Button } from '$lib/components/ui/button';
  import { AlertTriangle } from 'lucide-svelte';
  
  interface Props {
    title?: string;
    message?: string;
    options?: string[];
    onSelect: (choice: string) => void;
  }
  
  let { 
    title = 'Confirm', 
    message = '', 
    options = ['Allow Once', 'Always Allow', 'Deny'],
    onSelect 
  }: Props = $props();
</script>

<div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
  <div class="bg-background border border-border rounded-lg p-4 w-[400px] shadow-lg">
    <div class="flex items-start gap-3 mb-4">
      <AlertTriangle class="h-5 w-5 text-orange-500 mt-0.5" />
      <div class="flex-1">
        <h3 class="font-semibold mb-2">{title}</h3>
        <p class="text-sm text-muted-foreground">{message}</p>
      </div>
    </div>
    
    <div class="flex gap-2 justify-end">
      {#each options as opt}
        <Button 
          size="sm" 
          variant={opt.toLowerCase().includes('deny') ? 'destructive' : 'default'}
          onclick={() => onSelect(opt)}
        >
          {opt}
        </Button>
      {/each}
    </div>
  </div>
</div>

<style>
  /* Prevent scrolling when dialog is open */
  :global(body:has(.fixed)) {
    overflow: hidden;
  }
</style>