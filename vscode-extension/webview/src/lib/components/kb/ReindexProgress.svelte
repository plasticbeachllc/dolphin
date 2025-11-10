<script lang="ts">
  import * as Card from '$lib/components/ui/card';
  import { Progress } from '$lib/components/ui/progress';
  import { Button } from '$lib/components/ui/button';
  import { Loader2, X } from 'lucide-svelte';
  import type { KBProgress } from '$lib/stores/kb-store';
  
  interface Props {
    progress: KBProgress | null;
    onCancel?: () => void;
  }
  
  let { progress, onCancel }: Props = $props();
  
  const progressPercent = $derived(
    progress && progress.total > 0
      ? Math.round((progress.current / progress.total) * 100)
      : 0
  );
  
  const hasProgress = $derived(progress !== null);
</script>

{#if hasProgress && progress}
  <Card.Root>
    <Card.Header>
      <Card.Title>
        <div class="flex items-center gap-2">
          <Loader2 class="h-4 w-4 animate-spin" />
          Rebuilding Index
        </div>
      </Card.Title>
    </Card.Header>
    <Card.Content>
      <div class="space-y-4">
        <!-- Overall Progress -->
        <div class="space-y-2">
          <div class="flex justify-between text-sm">
            <span>Processing files...</span>
            <span>{progress.current}/{progress.total}</span>
          </div>
          <Progress value={progressPercent} />
        </div>
        
        <!-- Current Status -->
        {#if progress.currentFile}
          <div class="rounded-lg bg-muted p-3">
            <p class="text-sm">
              <span class="font-medium">Current:</span>
              {progress.currentFile}
            </p>
          </div>
        {/if}
        
        <!-- Stats -->
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p class="text-muted-foreground">Indexed</p>
            <p class="font-semibold">{progress.indexed.toLocaleString()} chunks</p>
          </div>
          <div>
            <p class="text-muted-foreground">Skipped</p>
            <p class="font-semibold">{progress.skipped.toLocaleString()} chunks</p>
          </div>
        </div>
        
        <!-- Cancel Button -->
        {#if onCancel}
          <Button 
            variant="outline" 
            class="w-full"
            onclick={onCancel}
          >
            <X class="mr-2 h-4 w-4" />
            Cancel Reindex
          </Button>
        {/if}
      </div>
    </Card.Content>
  </Card.Root>
{/if}