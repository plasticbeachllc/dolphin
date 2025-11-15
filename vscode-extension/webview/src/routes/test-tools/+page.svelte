<script lang="ts">
  import { ToolCallCard } from '$lib/components/tools';
  import { Button } from '$lib/components/ui/button';
  import { Separator } from '$lib/components/ui/separator';

  type ToolStatus = 'running' | 'success' | 'error';

  type ToolCallState = {
    tool: string;
    input: Record<string, unknown>;
    status: ToolStatus;
    result?: Record<string, unknown>;
    error?: string;
    executionTime?: number;
  };

  // Test data for different tool scenarios
  let runningTool = $state<ToolCallState>({
    tool: 'search_knowledge',
    input: { query: 'authentication patterns', top_k: 10 },
    status: 'running'
  });

  let successTool = $state<ToolCallState>({
    tool: 'read_files',
    input: { paths: ['src/auth.ts', 'src/user.ts'], max_size_bytes: 1048576 },
    status: 'success',
    result: {
      files: [
        { path: 'src/auth.ts', size_bytes: 2048, line_count: 87 },
        { path: 'src/user.ts', size_bytes: 1536, line_count: 64 }
      ],
      summary: { total_requested: 2, successful: 2, failed: 0 }
    },
    executionTime: 247
  });

  let errorTool = $state<ToolCallState>({
    tool: 'file_write',
    input: { path: '/etc/protected.txt', content: 'test' },
    status: 'error',
    error: 'Access denied: /etc/protected.txt is outside workspace',
    executionTime: 12
  });

  let allToolTypes = $state<ToolCallState[]>([
    {
      tool: 'search_knowledge',
      input: { query: 'user authentication' },
      status: 'success',
      result: { hits: 5, total_time_ms: 156 },
      executionTime: 156
    },
    {
      tool: 'kb_search',
      input: { query: 'database schema' },
      status: 'success',
      result: { hits: 3 },
      executionTime: 89
    },
    {
      tool: 'fetch_chunk',
      input: { chunk_id: 'chunk-abc123' },
      status: 'success',
      result: { content: 'function authenticate(user) { ... }' },
      executionTime: 45
    },
    {
      tool: 'fetch_lines',
      input: { repo: 'main', path: 'src/app.ts', start: 1, end: 50 },
      status: 'success',
      result: { lines: 50 },
      executionTime: 67
    },
    {
      tool: 'apply_diff',
      input: { path: 'src/auth.ts', diff: '...' },
      status: 'running'
    }
  ]);

  // Simulate tool completion
  function simulateCompletion() {
    runningTool.status = 'success';
    runningTool.result = { hits: 10, files: ['auth.ts', 'user.ts', 'db.ts'] };
    runningTool.executionTime = 1247;
  }

  function resetTests() {
    runningTool = {
      tool: 'search_knowledge',
      input: { query: 'authentication patterns', top_k: 10 },
      status: 'running'
    };
  }
</script>

<div class="container mx-auto p-6 max-w-4xl">
  <h1 class="text-3xl font-bold mb-2">ToolCallCard Component Test Page</h1>
  <p class="text-muted-foreground mb-6">
    Interactive examples of the ToolCallCard component in different states (v0 - no streaming)
  </p>

  <div class="space-y-8">
    <!-- Test Controls -->
    <div class="flex gap-2">
      <Button onclick={simulateCompletion}>Complete Running Tool</Button>
      <Button onclick={resetTests} variant="outline">Reset Tests</Button>
    </div>

    <Separator />

    <!-- Running State -->
    <section>
      <h2 class="text-xl font-semibold mb-3">Running State</h2>
      <p class="text-sm text-muted-foreground mb-3">
        Tool is currently executing. Click "Complete Running Tool" to see it finish.
      </p>
      <ToolCallCard {...runningTool} collapsed={false} />
    </section>

    <Separator />

    <!-- Success State -->
    <section>
      <h2 class="text-xl font-semibold mb-3">Success State</h2>
      <p class="text-sm text-muted-foreground mb-3">
        Tool completed successfully with results and execution time.
      </p>
      <ToolCallCard {...successTool} collapsed={false} />
    </section>

    <Separator />

    <!-- Error State -->
    <section>
      <h2 class="text-xl font-semibold mb-3">Error State</h2>
      <p class="text-sm text-muted-foreground mb-3">
        Tool encountered an error during execution.
      </p>
      <ToolCallCard {...errorTool} collapsed={false} />
    </section>

    <Separator />

    <!-- All Tool Types -->
    <section>
      <h2 class="text-xl font-semibold mb-3">All Available Tool Types</h2>
      <p class="text-sm text-muted-foreground mb-3">
        Click any card to expand and see details. Each tool has a unique icon (v0 tools only).
      </p>
      <div class="space-y-3">
        {#each allToolTypes as tool}
          <ToolCallCard {...tool} />
        {/each}
      </div>
    </section>

    <!-- Testing Instructions -->
    <Separator />
    <section class="bg-muted/30 p-4 rounded-lg">
      <h3 class="font-semibold mb-2">Testing Instructions</h3>
      <ul class="space-y-2 text-sm">
        <li>✓ Click cards to toggle expand/collapse (smooth animation)</li>
        <li>✓ Verify status indicators (spinner, checkmark, X)</li>
        <li>✓ Check color-coded borders (blue=running, green=success, red=error)</li>
        <li>✓ Test keyboard navigation (Tab to focus, Enter/Space to toggle)</li>
        <li>✓ Verify execution time badges display correctly</li>
        <li>✓ Verify JSON formatting in input/result sections</li>
        <li>✓ Test with different tool icons (emoji should display)</li>
        <li>✓ Test expand/collapse animation</li>
      </ul>
    </section>
  </div>
</div>

<style>
  .container {
    min-height: 100vh;
  }
</style>
