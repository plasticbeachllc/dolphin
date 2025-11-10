# Knowledge Base Reindexing UI Specification

## Overview
This document specifies the UI components and flows for managing KB reindexing with user confirmation dialogs to prevent accidental costly operations.

## Component Architecture

### 1. KB Status Bar Enhancement
**Location:** `vscode-extension/src/kb/status-bar.ts`

**Current States:**
- Ready (with chunk count)
- Indexing (with progress)
- Offline
- Degraded

**New States to Add:**
- Stale (needs reindex)
- Reindexing (full rebuild in progress)

### 2. KB Management Panel (New)
**Location:** `vscode-extension/webview/src/lib/components/kb/KBManagementPanel.svelte`

**Component Structure:**
```svelte
<Card>
  <CardHeader>
    <CardTitle>Knowledge Base Status</CardTitle>
    <CardDescription>Manage your workspace index</CardDescription>
  </CardHeader>
  <CardContent>
    <!-- Status Display -->
    <div class="space-y-4">
      <StatusBadge status={kbStatus} />
      <StatsGrid stats={kbStats} />
      <ActionButtons />
    </div>
  </CardContent>
</Card>
```

**Status Badge Component:**
```svelte
<!-- Uses shadcn-svelte Badge -->
<Badge variant={variantForStatus}>
  <Icon name={iconForStatus} />
  {statusText}
</Badge>

<!-- Variants:
  - "default" (Ready)
  - "secondary" (Indexing)
  - "destructive" (Offline/Error)
  - "outline" (Stale)
-->
```

**Stats Grid:**
```svelte
<div class="grid grid-cols-2 gap-4">
  <StatCard label="Files Indexed" value={stats.filesCount} />
  <StatCard label="Total Chunks" value={stats.chunksCount} />
  <StatCard label="Last Updated" value={stats.lastUpdated} />
  <StatCard label="Model" value={stats.embedModel} />
</div>
```

### 3. Reindex Confirmation Dialog
**Location:** `vscode-extension/webview/src/lib/components/kb/ReindexDialog.svelte`

**Component Structure:**
```svelte
<AlertDialog bind:open={confirmDialogOpen}>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>
        <Icon name="alert-triangle" class="text-warning" />
        Rebuild Knowledge Base Index?
      </AlertDialogTitle>
      <AlertDialogDescription>
        <div class="space-y-4">
          <p>This will completely rebuild the index for this workspace.</p>
          
          <!-- Cost Warning -->
          <Alert variant="destructive">
            <AlertCircle class="h-4 w-4" />
            <AlertTitle>Cost Warning</AlertTitle>
            <AlertDescription>
              This operation will re-embed all chunks and may incur API costs.
              <br/>
              Estimated: ~{estimatedCost} tokens (${costEstimate} USD)
            </AlertDescription>
          </Alert>

          <!-- Impact Summary -->
          <div class="rounded-lg border p-4 space-y-2">
            <h4 class="font-semibold text-sm">Impact Summary:</h4>
            <ul class="text-sm space-y-1">
              <li>• {stats.filesCount} files will be reprocessed</li>
              <li>• {stats.chunksCount} chunks will be re-embedded</li>
              <li>• Existing index will be cleared</li>
              <li>• Search unavailable during rebuild (~{estimatedTime})</li>
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
              class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              I understand this will incur embedding costs
            </Label>
          </div>
        </div>
      </AlertDialogDescription>
    </AlertDialogHeader>
    
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction 
        disabled={!userConfirmed}
        on:click={handleReindexConfirm}
      >
        <Icon name="refresh-cw" class="mr-2" />
        Rebuild Index
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

### 4. Incremental vs Full Reindex Options
**Location:** Same dialog, extended with options

```svelte
<RadioGroup bind:value={reindexMode}>
  <div class="space-y-3">
    <!-- Incremental Update -->
    <div class="flex items-start space-x-3 rounded-lg border p-4">
      <RadioGroupItem value="incremental" id="incremental" />
      <div class="space-y-1">
        <Label for="incremental" class="font-medium">
          Incremental Update (Recommended)
        </Label>
        <p class="text-sm text-muted-foreground">
          Only reprocess changed files since last index
        </p>
        <Badge variant="secondary">Free - Uses deduplication</Badge>
      </div>
    </div>

    <!-- Full Reindex -->
    <div class="flex items-start space-x-3 rounded-lg border p-4">
      <RadioGroupItem value="full" id="full" />
      <div class="space-y-1">
        <Label for="full" class="font-medium">
          Full Rebuild
        </Label>
        <p class="text-sm text-muted-foreground">
          Clear index and reprocess all files from scratch
        </p>
        <Badge variant="destructive">
          <Icon name="alert-circle" class="mr-1 h-3 w-3" />
          Cost: ~${fullReindexCost} USD
        </Badge>
      </div>
    </div>
  </div>
</RadioGroup>
```

### 5. Reindex Progress Panel
**Location:** `vscode-extension/webview/src/lib/components/kb/ReindexProgress.svelte`

```svelte
<Card>
  <CardHeader>
    <CardTitle>
      <Icon name="loader-2" class="animate-spin" />
      Rebuilding Index
    </CardTitle>
  </CardHeader>
  <CardContent>
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
      <div class="rounded-lg bg-muted p-3">
        <p class="text-sm">
          <span class="font-medium">Current:</span>
          {currentFile}
        </p>
      </div>

      <!-- Stats -->
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <p class="text-muted-foreground">Indexed</p>
          <p class="font-semibold">{stats.indexed} chunks</p>
        </div>
        <div>
          <p class="text-muted-foreground">Skipped</p>
          <p class="font-semibold">{stats.skipped} chunks</p>
        </div>
      </div>

      <!-- Cancel Button -->
      <Button 
        variant="outline" 
        class="w-full"
        on:click={handleCancelReindex}
      >
        <Icon name="x" class="mr-2" />
        Cancel Reindex
      </Button>
    </div>
  </CardContent>
</Card>
```

### 6. Action Buttons Panel
**Location:** Part of KB Management Panel

```svelte
<div class="flex flex-col gap-2">
  <!-- Quick Sync (Incremental) -->
  <Button 
    variant="default" 
    class="w-full"
    on:click={handleIncrementalSync}
    disabled={isIndexing}
  >
    <Icon name="refresh-cw" class="mr-2 h-4 w-4" />
    Sync Changes
  </Button>

  <!-- Full Reindex (with warning) -->
  <Button 
    variant="outline" 
    class="w-full"
    on:click={() => confirmDialogOpen = true}
    disabled={isIndexing}
  >
    <Icon name="database" class="mr-2 h-4 w-4" />
    Rebuild Index...
  </Button>

  <!-- View Status -->
  <Button 
    variant="ghost" 
    class="w-full"
    on:click={handleViewStatus}
  >
    <Icon name="info" class="mr-2 h-4 w-4" />
    View Details
  </Button>
</div>
```

## State Management

### KB Status Store
**Location:** `vscode-extension/webview/src/lib/stores/kb-store.ts`

```typescript
interface KBStatus {
  initialized: boolean;
  repoName: string | null;
  status: 'ready' | 'indexing' | 'reindexing' | 'offline' | 'stale';
  stats: {
    filesCount: number;
    chunksCount: number;
    lastUpdated: string;
    embedModel: string;
  };
  progress?: {
    current: number;
    total: number;
    currentFile: string;
    indexed: number;
    skipped: number;
  };
}

const kbStore = writable<KBStatus>({
  initialized: false,
  repoName: null,
  status: 'offline',
  stats: {
    filesCount: 0,
    chunksCount: 0,
    lastUpdated: 'Never',
    embedModel: 'large'
  }
});
```

## API Integration

### New Backend Endpoints Needed

#### 1. GET `/v1/repos/{repo}/stats`
Returns repository statistics for cost estimation:
```json
{
  "filesCount": 1234,
  "chunksCount": 5678,
  "totalTokens": 1500000,
  "embedModel": "large",
  "lastIndexed": "2024-01-15T10:30:00Z",
  "needsReindex": false
}
```

#### 2. POST `/v1/repos/{repo}/reindex`
Triggers full reindex with confirmation:
```json
{
  "mode": "full" | "incremental",
  "confirmed": true,
  "clearExisting": true
}
```

#### 3. DELETE `/v1/repos/{repo}/index`
Clears index (requires confirmation):
```json
{
  "confirmed": true
}
```

### Extension Commands

#### 1. `dolphin.kb.reindex`
Opens reindex dialog with cost estimation

#### 2. `dolphin.kb.syncChanges`
Performs incremental sync (no confirmation needed)

#### 3. `dolphin.kb.clearIndex`
Clears index with confirmation dialog

## User Flows

### Flow 1: Incremental Sync (No Confirmation)
1. User clicks "Sync Changes" button
2. Extension detects changed files
3. Indexes only changed files
4. Shows progress toast
5. Updates status bar when complete

### Flow 2: Full Reindex (With Confirmation)
1. User clicks "Rebuild Index..." button
2. Extension fetches current stats from API
3. Dialog opens with:
   - Cost estimation
   - Impact summary
   - Confirmation checkbox
4. User reads warning and checks confirmation
5. User clicks "Rebuild Index"
6. Extension sends reindex request
7. Progress panel shows live updates
8. Status bar reflects reindexing state
9. Completion notification shown

### Flow 3: Clear Index (With Confirmation)
1. User clicks "Clear Index" from command palette
2. Warning dialog appears:
   - Explains all data will be deleted
   - Shows current chunk count
   - Requires confirmation
3. User confirms
4. Index cleared
5. Status shows "Not Indexed"

## Cost Estimation Logic

```typescript
function estimateReindexCost(stats: KBStats): CostEstimate {
  // Using Voyage AI pricing (example)
  const COST_PER_MILLION_TOKENS = 0.12; // $0.12 per 1M tokens
  
  const estimatedTokens = stats.totalTokens;
  const costUSD = (estimatedTokens / 1_000_000) * COST_PER_MILLION_TOKENS;
  
  // Estimate time (rough calculation)
  const CHUNKS_PER_SECOND = 10;
  const estimatedSeconds = Math.ceil(stats.chunksCount / CHUNKS_PER_SECOND);
  
  return {
    tokens: estimatedTokens,
    costUSD: costUSD.toFixed(2),
    estimatedTime: formatDuration(estimatedSeconds)
  };
}
```

## shadcn-svelte Components Used

### Required Components:
- `Alert` / `AlertDialog` - Warnings and confirmations
- `Badge` - Status indicators
- `Button` - Actions
- `Card` / `CardHeader` / `CardContent` - Containers
- `Checkbox` - Confirmation checkbox
- `Dialog` - Modal dialogs
- `Label` - Form labels
- `Progress` - Progress bars
- `RadioGroup` / `RadioGroupItem` - Options selection
- `Separator` - Visual dividers

### Installation:
```bash
npx shadcn-svelte@latest add alert alert-dialog badge button card checkbox dialog label progress radio-group separator
```

## Accessibility

- All interactive elements have proper ARIA labels
- Keyboard navigation fully supported
- Screen reader announcements for status changes
- Focus management in dialogs
- High contrast mode support

## Error Handling

### Error States:
1. **API Unavailable:** Show offline status with retry option
2. **Reindex Failed:** Show error details, suggest incremental sync
3. **Out of Memory:** Show warning, suggest smaller batch size
4. **Network Timeout:** Show retry dialog

### Error Dialog Template:
```svelte
<Alert variant="destructive">
  <AlertCircle class="h-4 w-4" />
  <AlertTitle>Reindex Failed</AlertTitle>
  <AlertDescription>
    {errorMessage}
    <br/>
    <Button variant="link" on:click={handleRetry}>
      Try Again
    </Button>
  </AlertDescription>
</Alert>
```

## Testing Checklist

- [ ] Cost estimation accuracy
- [ ] Confirmation dialog prevents accidental reindex
- [ ] Progress updates in real-time
- [ ] Cancel operation works correctly
- [ ] Error states handle gracefully
- [ ] Keyboard navigation works
- [ ] Screen reader compatibility
- [ ] Theme consistency (light/dark)
- [ ] Mobile-responsive layout

## Implementation Order

1. **Phase 1:** Backend API endpoints for stats and reindex
2. **Phase 2:** KB status store and state management
3. **Phase 3:** Basic KB management panel
4. **Phase 4:** Reindex confirmation dialog
5. **Phase 5:** Progress tracking and display
6. **Phase 6:** Error handling and recovery
7. **Phase 7:** Testing and polish

## Next Steps

1. Review and approve this specification
2. Get cost estimation formulas from KB team
3. Implement backend API endpoints
4. Build UI components with shadcn-svelte
5. Integration testing with real workspaces
6. User acceptance testing