<script lang="ts">
  import { onMount } from 'svelte';
  import * as Card from '$lib/components/ui/card';
  import { Badge } from '$lib/components/ui/badge';
  import { Button } from '$lib/components/ui/button';
  import { Database, RefreshCw, Info, AlertCircle } from 'lucide-svelte';
  import { kbStore, isIndexing, canReindex, kbActions } from '$lib/stores/kb-store';
  import { kbApi } from '$lib/api/kb-api';
  import KBStatusBadge from './KBStatusBadge.svelte';
  import KBStatsGrid from './KBStatsGrid.svelte';
  import ReindexDialog from './ReindexDialog.svelte';
  import ReindexProgress from './ReindexProgress.svelte';
  
  let confirmDialogOpen = $state(false);
  let statsError = $state<string | null>(null);
  
  // Load KB stats on mount
  onMount(async () => {
    await loadStats();
  });
  
  async function loadStats() {
    try {
      statsError = null;
      
      // Get repo name from store - don't proceed if not set
      const repoName = $kbStore.repoName;
      if (!repoName) {
        statsError = 'No repository configured. Please open a workspace folder.';
        kbActions.setStatus('offline');
        return;
      }
      
      const stats = await kbApi.getRepoStats(repoName);
      
      kbActions.initialize(repoName, {
        filesCount: stats.files_count,
        chunksCount: stats.chunks_count,
        totalTokens: stats.total_tokens,
        embedModel: stats.embed_model,
        lastUpdated: stats.last_indexed || 'Never'
      });
      
      // Set status based on stats
      if (stats.needs_reindex) {
        kbActions.markStale();
      } else if (stats.chunks_count > 0) {
        kbActions.setStatus('ready');
      } else {
        kbActions.setStatus('offline');
      }
    } catch (error) {
      console.error('[KBManagementPanel] Failed to load stats:', error);
      statsError = error instanceof Error ? error.message : 'Failed to load KB stats';
      kbActions.setStatus('offline');
    }
  }
  
  async function handleIncrementalSync() {
    try {
      const repoName = $kbStore.repoName;
      if (!repoName) {
        statsError = 'No repository configured. Please open a workspace folder.';
        return;
      }
      
      kbActions.setStatus('indexing');
      
      const response = await kbApi.triggerReindex(repoName, {
        mode: 'incremental',
        confirmed: true,
        clear_existing: false
      });
      
      // Start polling for progress
      await kbApi.pollIndexStatus(response.task_id, (status) => {
        kbActions.updateProgress({
          current: status.progress,
          total: status.total,
          currentFile: '',
          indexed: status.indexed,
          skipped: status.skipped
        });
        
        if (status.status === 'completed') {
          kbActions.setStatus('ready');
          kbActions.clearProgress();
          loadStats(); // Refresh stats
        } else if (status.status === 'failed') {
          kbActions.setStatus('offline');
          kbActions.clearProgress();
          statsError = status.error || 'Indexing failed';
        }
      });
    } catch (error) {
      console.error('[KBManagementPanel] Incremental sync failed:', error);
      statsError = error instanceof Error ? error.message : 'Sync failed';
      kbActions.setStatus('offline');
      kbActions.clearProgress();
    }
  }
  
  function handleRebuildIndex() {
    confirmDialogOpen = true;
  }
  
  function handleViewStatus() {
    // TODO: Navigate to detailed KB status view
    console.log('[KBManagementPanel] View status clicked');
  }
  
  async function handleReindexConfirmed(mode: 'full' | 'incremental', clearExisting: boolean) {
    try {
      const repoName = $kbStore.repoName;
      if (!repoName) {
        statsError = 'No repository configured. Please open a workspace folder.';
        return;
      }
      
      kbActions.setStatus(mode === 'full' ? 'reindexing' : 'indexing');
      
      const response = await kbApi.triggerReindex(repoName, {
        mode,
        confirmed: true,
        clear_existing: clearExisting
      });
      
      // Start polling for progress
      await kbApi.pollIndexStatus(response.task_id, (status) => {
        kbActions.updateProgress({
          current: status.progress,
          total: status.total,
          currentFile: '',
          indexed: status.indexed,
          skipped: status.skipped
        });
        
        if (status.status === 'completed') {
          kbActions.setStatus('ready');
          kbActions.clearProgress();
          loadStats(); // Refresh stats
        } else if (status.status === 'failed') {
          kbActions.setStatus('offline');
          kbActions.clearProgress();
          statsError = status.error || 'Indexing failed';
        }
      });
    } catch (error) {
      console.error('[KBManagementPanel] Reindex failed:', error);
      statsError = error instanceof Error ? error.message : 'Reindex failed';
      kbActions.setStatus('offline');
      kbActions.clearProgress();
    }
  }
  
  function handleCancelReindex() {
    // TODO: Implement cancel API call
    console.log('[KBManagementPanel] Cancel reindex requested');
    kbActions.clearProgress();
    kbActions.setStatus('ready');
  }
</script>

<Card.Root>
  <Card.Header>
    <Card.Title>Knowledge Base Status</Card.Title>
    <Card.Description>Manage your workspace index</Card.Description>
  </Card.Header>
  <Card.Content>
    <!-- Show progress panel if indexing -->
    {#if $isIndexing && $kbStore.progress}
      <ReindexProgress
        progress={$kbStore.progress}
        onCancel={handleCancelReindex}
      />
    {:else}
      <div class="space-y-4">
        <!-- Error Alert -->
      {#if statsError}
        <div class="rounded-lg border border-destructive bg-destructive/10 p-3 flex items-start gap-2">
          <AlertCircle class="h-4 w-4 text-destructive mt-0.5" />
          <div class="flex-1">
            <p class="text-sm font-medium text-destructive">Error</p>
            <p class="text-xs text-destructive/80 mt-1">{statsError}</p>
            <Button 
              variant="link" 
              size="sm" 
              class="h-auto p-0 text-xs text-destructive hover:text-destructive/80"
              onclick={loadStats}
            >
              Try Again
            </Button>
          </div>
        </div>
      {/if}
      
      <!-- Status Badge -->
      <KBStatusBadge status={$kbStore.status} />
      
      <!-- Stats Grid -->
      <KBStatsGrid
        filesCount={$kbStore.stats.filesCount}
        chunksCount={$kbStore.stats.chunksCount}
        lastUpdated={$kbStore.stats.lastUpdated || 'Never'}
        embedModel={$kbStore.stats.embedModel}
      />
      
      <!-- Action Buttons -->
      <div class="flex flex-col gap-2">
        <!-- Quick Sync (Incremental) -->
        <Button 
          variant="default" 
          class="w-full"
          onclick={handleIncrementalSync}
          disabled={$isIndexing}
        >
          <RefreshCw class="mr-2 h-4 w-4" />
          Sync Changes
        </Button>
        
        <!-- Full Reindex (with warning) -->
        <Button 
          variant="outline" 
          class="w-full"
          onclick={handleRebuildIndex}
          disabled={$isIndexing}
        >
          <Database class="mr-2 h-4 w-4" />
          Rebuild Index...
        </Button>
        
        <!-- View Status -->
        <Button 
          variant="ghost" 
          class="w-full"
          onclick={handleViewStatus}
        >
          <Info class="mr-2 h-4 w-4" />
          View Details
        </Button>
        </div>
      </div>
    {/if}
  </Card.Content>
</Card.Root>

<!-- Reindex Confirmation Dialog -->
<ReindexDialog 
  bind:open={confirmDialogOpen}
  stats={{
    filesCount: $kbStore.stats.filesCount,
    chunksCount: $kbStore.stats.chunksCount,
    totalTokens: $kbStore.stats.totalTokens
  }}
  onConfirm={handleReindexConfirmed}
/>