<script lang="ts">
  import { FileText, Layers, Clock, Cpu } from 'lucide-svelte';

  interface Props {
    filesCount: number;
    chunksCount: number;
    lastUpdated: string | null;
    embedModel: string;
  }

  let { filesCount, chunksCount, lastUpdated, embedModel }: Props = $props();

  function formatLastUpdated(timestamp: string | null): string {
    if (!timestamp || timestamp === 'Never') return 'Never';

    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;

      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return 'Unknown';
    }
  }

  const formattedLastUpdated = $derived(formatLastUpdated(lastUpdated));
</script>

<div class="grid grid-cols-2 gap-4">
  <!-- Files Indexed -->
  <div class="rounded-lg border p-3 space-y-1">
    <div class="flex items-center gap-1.5 text-muted-foreground">
      <FileText class="h-3.5 w-3.5" />
      <span class="text-xs">Files Indexed</span>
    </div>
    <p class="text-lg font-semibold">{(filesCount ?? 0).toLocaleString()}</p>
  </div>

  <!-- Total Chunks -->
  <div class="rounded-lg border p-3 space-y-1">
    <div class="flex items-center gap-1.5 text-muted-foreground">
      <Layers class="h-3.5 w-3.5" />
      <span class="text-xs">Total Chunks</span>
    </div>
    <p class="text-lg font-semibold">{(chunksCount ?? 0).toLocaleString()}</p>
  </div>

  <!-- Last Updated -->
  <div class="rounded-lg border p-3 space-y-1">
    <div class="flex items-center gap-1.5 text-muted-foreground">
      <Clock class="h-3.5 w-3.5" />
      <span class="text-xs">Last Updated</span>
    </div>
    <p class="text-sm font-medium">{formattedLastUpdated}</p>
  </div>

  <!-- Model -->
  <div class="rounded-lg border p-3 space-y-1">
    <div class="flex items-center gap-1.5 text-muted-foreground">
      <Cpu class="h-3.5 w-3.5" />
      <span class="text-xs">Model</span>
    </div>
    <p class="text-sm font-medium capitalize">{embedModel || 'unknown'}</p>
  </div>
</div>