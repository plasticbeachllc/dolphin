<script lang="ts">
  import * as Card from '$lib/components/ui/card';
  import { Progress } from '$lib/components/ui/progress';
  import { Button } from '$lib/components/ui/button';
  import { Loader2, X, Check } from 'lucide-svelte';
  
  // Mock progress data
  let progress = $state({
    current: 42,
    total: 150,
    currentFile: 'src/components/MyComponent.tsx',
    indexed: 1234,
    skipped: 567
  });
  
  const progressPercent = $derived(
    progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0
  );
</script>

<div class="h-screen overflow-y-auto">
  <div class="p-6 space-y-8 max-w-4xl mx-auto">
    <div>
      <h1 class="text-2xl font-bold mb-2">Progress Bar Design Options</h1>
      <p class="text-sm text-muted-foreground">
        Different layouts for the reindex progress indicator
      </p>
    </div>

  <!-- Option 1: Compact Inline (Current) -->
  <div class="space-y-2">
    <h2 class="text-lg font-semibold">Option 1: Compact Inline (Current)</h2>
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
          <Button variant="outline" class="w-full">
            <X class="mr-2 h-4 w-4" />
            Cancel Reindex
          </Button>
        </div>
      </Card.Content>
    </Card.Root>
  </div>

  <!-- Option 2: Minimal Inline (Condensed) -->
  <div class="space-y-2">
    <h2 class="text-lg font-semibold">Option 2: Minimal Inline (Condensed)</h2>
    <div class="rounded-lg border p-4 space-y-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Loader2 class="h-4 w-4 animate-spin" />
          <span class="font-medium">Rebuilding Index</span>
        </div>
        <span class="text-sm text-muted-foreground">{progress.current}/{progress.total} files</span>
      </div>
      
      <Progress value={progressPercent} />
      
      <div class="flex items-center justify-between text-xs text-muted-foreground">
        <span>{progress.indexed.toLocaleString()} indexed • {progress.skipped.toLocaleString()} skipped</span>
        <Button variant="ghost" size="sm" class="h-6 px-2">
          <X class="h-3 w-3 mr-1" />
          Cancel
        </Button>
      </div>
    </div>
  </div>

  <!-- Option 3: Status Bar Style (VSCode-like) -->
  <div class="space-y-2">
    <h2 class="text-lg font-semibold">Option 3: Status Bar Style (VSCode-like)</h2>
    <div class="rounded-lg border bg-muted/30">
      <div class="flex items-center gap-4 p-3">
        <div class="flex items-center gap-2 flex-1">
          <Loader2 class="h-3.5 w-3.5 animate-spin" />
          <span class="text-sm font-medium">Indexing: {progress.current}/{progress.total}</span>
          <span class="text-xs text-muted-foreground">({progressPercent}%)</span>
        </div>
        
        <div class="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{progress.indexed.toLocaleString()} indexed</span>
          <span>{progress.skipped.toLocaleString()} skipped</span>
        </div>
        
        <Button variant="ghost" size="sm" class="h-7">
          <X class="h-3 w-3" />
        </Button>
      </div>
      <Progress value={progressPercent} class="h-1 rounded-none" />
    </div>
  </div>

  <!-- Option 4: Horizontal Split -->
  <div class="space-y-2">
    <h2 class="text-lg font-semibold">Option 4: Horizontal Split</h2>
    <Card.Root>
      <Card.Content class="p-0">
        <div class="grid grid-cols-[1fr_auto] divide-x">
          <!-- Left: Progress -->
          <div class="p-4 space-y-3">
            <div class="flex items-center gap-2">
              <Loader2 class="h-4 w-4 animate-spin" />
              <span class="font-medium">Rebuilding Index</span>
            </div>
            
            <div class="space-y-1">
              <div class="flex justify-between text-sm">
                <span class="text-muted-foreground">Progress</span>
                <span class="font-medium">{progress.current}/{progress.total} files</span>
              </div>
              <Progress value={progressPercent} />
            </div>
            
            {#if progress.currentFile}
              <p class="text-xs text-muted-foreground truncate">
                {progress.currentFile}
              </p>
            {/if}
          </div>
          
          <!-- Right: Stats & Actions -->
          <div class="p-4 space-y-3 min-w-[180px]">
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-muted-foreground">Indexed</span>
                <span class="font-medium">{progress.indexed.toLocaleString()}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-muted-foreground">Skipped</span>
                <span class="font-medium">{progress.skipped.toLocaleString()}</span>
              </div>
            </div>
            
            <Button variant="outline" size="sm" class="w-full">
              <X class="mr-2 h-3 w-3" />
              Cancel
            </Button>
          </div>
        </div>
      </Card.Content>
    </Card.Root>
  </div>

  <!-- Option 5: Compact Banner (Toast-like) -->
  <div class="space-y-2">
    <h2 class="text-lg font-semibold">Option 5: Compact Banner (Toast-like)</h2>
    <div class="rounded-lg border bg-card shadow-sm max-w-md">
      <div class="p-3 space-y-2">
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-start gap-2 flex-1 min-w-0">
            <Loader2 class="h-4 w-4 animate-spin mt-0.5 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <p class="font-medium text-sm">Rebuilding Index</p>
              <p class="text-xs text-muted-foreground">
                {progress.current} of {progress.total} files • {progressPercent}%
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" class="h-6 w-6 p-0">
            <X class="h-3 w-3" />
          </Button>
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
  </div>

  <!-- Option 6: Vertical Stack (Mobile-friendly) -->
  <div class="space-y-2">
    <h2 class="text-lg font-semibold">Option 6: Vertical Stack (Mobile-friendly)</h2>
    <div class="rounded-lg border max-w-sm">
      <div class="p-4 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Loader2 class="h-4 w-4 animate-spin" />
            <span class="font-medium text-sm">Rebuilding Index</span>
          </div>
        </div>
        
        <div class="space-y-1">
          <Progress value={progressPercent} />
          <p class="text-xs text-muted-foreground text-center">
            {progress.current}/{progress.total} files ({progressPercent}%)
          </p>
        </div>
        
        <div class="grid grid-cols-2 gap-3 text-center">
          <div class="rounded-md bg-muted p-2">
            <p class="text-xs text-muted-foreground">Indexed</p>
            <p class="text-sm font-semibold">{progress.indexed.toLocaleString()}</p>
          </div>
          <div class="rounded-md bg-muted p-2">
            <p class="text-xs text-muted-foreground">Skipped</p>
            <p class="text-sm font-semibold">{progress.skipped.toLocaleString()}</p>
          </div>
        </div>
        
        <Button variant="outline" size="sm" class="w-full">
          <X class="mr-2 h-3 w-3" />
          Cancel Reindex
        </Button>
        </div>
      </div>
    </div>
  </div>
</div>