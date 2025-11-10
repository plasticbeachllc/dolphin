<script lang="ts">
  import * as AlertDialog from '$lib/components/ui/alert-dialog';
  import * as Alert from '$lib/components/ui/alert';
  import * as RadioGroup from '$lib/components/ui/radio-group';
  import { Checkbox } from '$lib/components/ui/checkbox';
  import { Label } from '$lib/components/ui/label';
  import { Badge } from '$lib/components/ui/badge';
  import { AlertTriangle, AlertCircle, RefreshCw } from 'lucide-svelte';
  
  interface Props {
    open: boolean;
    stats: {
      filesCount: number;
      chunksCount: number;
      totalTokens: number;
    };
    onConfirm: (mode: 'full' | 'incremental', clearExisting: boolean) => void;
  }
  
  let { open = $bindable(), stats, onConfirm }: Props = $props();
  
  let reindexMode = $state<'incremental' | 'full'>('incremental');
  let userConfirmed = $state(false);
  
  function handleConfirm() {
    if (!userConfirmed && reindexMode === 'full') return;
    
    const clearExisting = reindexMode === 'full';
    onConfirm(reindexMode, clearExisting);
    
    // Reset state
    open = false;
    reindexMode = 'incremental';
    userConfirmed = false;
  }
  
  function handleCancel() {
    open = false;
    reindexMode = 'incremental';
    userConfirmed = false;
  }
  
  // Reset confirmation when mode changes
  $effect(() => {
    if (reindexMode === 'incremental') {
      userConfirmed = false;
    }
  });
</script>

<AlertDialog.Root bind:open>
  <AlertDialog.Content>
    <AlertDialog.Header>
      <AlertDialog.Title>
        <div class="flex items-center gap-2">
          <AlertTriangle class="h-5 w-5 text-warning" />
          Rebuild Knowledge Base Index?
        </div>
      </AlertDialog.Title>
      <AlertDialog.Description>
        <div class="space-y-4 mt-4">
          <p class="text-sm">Choose how to update your workspace index:</p>
          
          <!-- Reindex Mode Selection -->>
          <RadioGroup.Root bind:value={reindexMode}>
            <div class="space-y-3">
              <!-- Incremental Update -->
              <div class="flex items-start space-x-3 rounded-lg border p-4 {reindexMode === 'incremental' ? 'border-primary' : ''}">
                <RadioGroup.Item value="incremental" id="incremental" class="mt-1" />
                <div class="space-y-1 flex-1">
                  <Label for="incremental" class="font-medium text-sm cursor-pointer">
                    Incremental Update (Recommended)
                  </Label>
                  <p class="text-xs text-muted-foreground">
                    Only reprocess changed files since last index. Uses deduplication to skip unchanged content.
                  </p>
                </div>
              </div>
              
              <!-- Full Reindex -->
              <div class="flex items-start space-x-3 rounded-lg border p-4 {reindexMode === 'full' ? 'border-destructive' : ''}">
                <RadioGroup.Item value="full" id="full" class="mt-1" />
                <div class="space-y-1 flex-1">
                  <Label for="full" class="font-medium text-sm cursor-pointer">
                    Full Rebuild
                  </Label>
                  <p class="text-xs text-muted-foreground">
                    Clear index and reprocess all files from scratch. This may take time for large repositories.
                  </p>
                </div>
              </div>
            </div>
          </RadioGroup.Root>
          
          {#if reindexMode === 'full'}
            <!-- Warning for Full Reindex -->
            <Alert.Root variant="destructive">
              <AlertCircle class="h-4 w-4" />
              <Alert.Title>Full Rebuild</Alert.Title>
              <Alert.Description>
                This will clear the existing index and reprocess all files. This operation may take time for large repositories.
              </Alert.Description>
            </Alert.Root>
            
            <!-- Impact Summary -->
            <div class="rounded-lg border p-4 space-y-2">
              <h4 class="font-semibold text-sm">What will happen:</h4>
              <ul class="text-sm space-y-1 text-muted-foreground">
                <li>• {stats.filesCount.toLocaleString()} files will be reprocessed</li>
                <li>• {stats.chunksCount.toLocaleString()} chunks will be re-embedded</li>
                <li>• Existing index will be cleared</li>
                <li>• Search may be temporarily unavailable</li>
              </ul>
            </div>
            
            <!-- Confirmation Checkbox -->
            <div class="flex items-center space-x-2">
              <Checkbox
                id="confirm-reindex"
                bind:checked={userConfirmed}
              />
              <Label
                for="confirm-reindex"
                class="text-sm font-medium leading-none cursor-pointer"
              >
                I understand this will rebuild the entire index
              </Label>
            </div>
          {:else}
            <!-- Incremental Info -->
            <div class="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 p-4 space-y-2">
              <h4 class="font-semibold text-sm text-green-900 dark:text-green-100">Incremental Update</h4>
              <ul class="text-sm space-y-1 text-green-700 dark:text-green-300">
                <li>• Only changed files are reprocessed</li>
                <li>• Deduplication prevents re-embedding unchanged content</li>
                <li>• Fast and efficient</li>
              </ul>
            </div>
          {/if}
        </div>
      </AlertDialog.Description>
    </AlertDialog.Header>
    
    <AlertDialog.Footer>
      <AlertDialog.Cancel onclick={handleCancel}>Cancel</AlertDialog.Cancel>
      <AlertDialog.Action 
        disabled={reindexMode === 'full' && !userConfirmed}
        onclick={handleConfirm}
      >
        <RefreshCw class="mr-2 h-4 w-4" />
        {reindexMode === 'full' ? 'Rebuild Index' : 'Update Index'}
      </AlertDialog.Action>
    </AlertDialog.Footer>
  </AlertDialog.Content>
</AlertDialog.Root>