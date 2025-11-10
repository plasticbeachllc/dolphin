<script lang="ts">
  import { Progress } from '$lib/components/ui/progress';
  import { Loader2, Check } from 'lucide-svelte';
  import type { KBProgress } from '$lib/stores/kb-store';
  
  interface Props {
    progress: KBProgress | null;
    onCancel?: () => void;
  }
  
  let { progress }: Props = $props();
  
  const progressPercent = $derived(
    progress && progress.total > 0
      ? Math.round((progress.current / progress.total) * 100)
      : 0
  );
  
  const hasProgress = $derived(progress !== null);
</script>

{#if hasProgress && progress}
  <div class="rounded-lg border bg-card shadow-sm">
    <div class="p-3 space-y-2">
      <div class="flex items-start gap-2">
        <Loader2 class="h-4 w-4 animate-spin mt-0.5 flex-shrink-0" />
        <div class="flex-1 min-w-0">
          <p class="font-medium text-sm">Rebuilding Index</p>
          <p class="text-xs text-muted-foreground">
            {progress.current} of {progress.total} files • {progressPercent}%
          </p>
        </div>
      </div>
      
      <Progress value={progressPercent} class="h-1.5" />
      
      <div class="flex gap-3 text-xs text-muted-foreground">
        <span class="flex items-center gap-1">
          <Check class="h-3 w-3" />
          {progress.indexed.toLocaleString()} indexed
        </span>
        <span>•</span>
        <span>{progress.skipped.toLocaleString()} skipped</span>
      </div>
    </div>
  </div>
{/if}