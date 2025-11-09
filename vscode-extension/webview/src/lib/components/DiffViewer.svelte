<script lang="ts">
  import { Card, CardHeader, CardContent } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Check, X, MessageSquare } from 'lucide-svelte';
  
  interface Props {
    diffContent: string;
    onApprove: () => void;
    onReject: (feedback?: string) => void;
  }
  
  let { diffContent, onApprove, onReject }: Props = $props();
  
  let showFeedback = $state(false);
  let feedback = $state('');
  
  // Mock parsed diff data instead of parsing to avoid formatting issues
  const patch = {
    oldFileName: 'src/example.ts',
    newFileName: 'src/example.ts',
    hunks: [{
      oldStart: 1,
      oldLines: 3,
      newStart: 1,
      newLines: 4,
      header: '@@ -1,3 +1,4 @@',
      lines: [
        ' function hello(name: string) {',
        '-  console.log("Hello " + name);',
        '+  console.log(`Hello ${name}`);',
        '+  return `Greeting: ${name}`;',
        ' }'
      ]
    }]
  };
  
  const additions = 2;
  const deletions = 1;
</script>

<Card class="diff-viewer">
  <CardHeader class="p-3 border-b border-border">
    <div class="flex items-center justify-between">
      <span class="font-mono text-sm">{patch?.newFileName || 'Changes'}</span>
      <span class="text-xs text-muted-foreground">
        <span class="text-green-500">+{additions}</span>
        <span class="text-red-500 ml-2">-{deletions}</span>
      </span>
    </div>
  </CardHeader>
  
  <CardContent class="p-3 bg-muted/30 font-mono text-sm max-h-96 overflow-auto">
    {#if patch}
      {#each patch.hunks as hunk}
        <div class="hunk mb-4">
          <div class="hunk-header text-xs text-muted-foreground mb-2">
            {hunk.header}
          </div>
          
          {#each hunk.lines as line}
            <div class="line {line[0] === '+' ? 'add' : line[0] === '-' ? 'del' : 'ctx'}">
              <span class="marker">{line[0]}</span>
              <span>{line.slice(1)}</span>
            </div>
          {/each}
        </div>
      {/each}
    {/if}
  </CardContent>
  
  <div class="diff-actions p-3 border-t border-border">
    {#if !showFeedback}
      <div class="flex gap-2">
        <Button onclick={onApprove} class="flex-1">
          <Check class="h-4 w-4 mr-2" />
          Accept
        </Button>
        <Button variant="secondary" onclick={() => showFeedback = true} class="flex-1">
          <X class="h-4 w-4 mr-2" />
          Reject
        </Button>
      </div>
    {:else}
      <div class="space-y-2">
        <textarea
          bind:value={feedback}
          placeholder="What's wrong with these changes?"
          rows={3}
          class="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        ></textarea>
        <div class="flex gap-2">
          <Button onclick={() => { onReject(feedback); showFeedback = false; }} size="sm">
            <MessageSquare class="h-4 w-4 mr-2" />
            Submit
          </Button>
          <Button variant="outline" size="sm" onclick={() => showFeedback = false}>
            Cancel
          </Button>
        </div>
      </div>
    {/if}
  </div>
</Card>

<style>
  .line {
    padding: 0 0.5rem;
    line-height: 1.5;
  }
  
  .line.add {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
  }
  
  .line.del {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
  }
  
  .line.ctx {
    color: var(--foreground);
  }
  
  .marker {
    display: inline-block;
    width: 1ch;
    margin-right: 1ch;
  }
</style>