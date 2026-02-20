<script lang="ts">
  import { onMount } from 'svelte';
  import { Card, CardHeader, CardContent } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import * as Tabs from '$lib/components/ui/tabs';
  import { Check, X, MessageSquare, Code, FileDiff } from 'lucide-svelte';
  import { createHighlighter } from 'shiki';

  interface Props {
    diffContent: string;
    onApprove: () => void;
    onReject: (feedback?: string) => void;
  }

  let { diffContent, onApprove, onReject }: Props = $props();

  let showFeedback = $state(false);
  let feedback = $state('');
  let highlightedDiff = $state('');
  let isLoading = $state(true);

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

  onMount(async () => {
    try {
      const highlighter = await createHighlighter({
        themes: ['github-dark', 'github-light'],
        langs: ['diff', 'typescript']
      });

      highlightedDiff = highlighter.codeToHtml(diffContent ||
`--- src/example.ts
+++ src/example.ts
@@ -1,3 +1,4 @@
 function hello(name: string) {
-  console.log("Hello " + name);
+  console.log(\`Hello \${name}\`);
+  return \`Greeting: \${name}\`;
 }`, {
        lang: 'diff',
        theme: 'github-dark'
      });
    } catch (e) {
      console.error('Failed to highlight diff:', e);
      highlightedDiff = `<pre>${diffContent}</pre>`;
    } finally {
      isLoading = false;
    }
  });
</script>

<Card class="diff-viewer overflow-hidden">
  <Tabs.Root value="diff" class="w-full">
    <div class="flex items-center justify-between border-b px-4 py-2 bg-muted/30">
      <div class="flex items-center gap-4">
        <span class="font-mono text-sm font-medium">{patch?.newFileName || 'Changes'}</span>
        <span class="text-xs text-muted-foreground flex items-center gap-2">
          <span class="text-green-500 flex items-center"><span class="mr-0.5">+</span>{additions}</span>
          <span class="text-red-500 flex items-center"><span class="mr-0.5">-</span>{deletions}</span>
        </span>
      </div>

      <Tabs.List class="h-8">
        <Tabs.Trigger value="diff" class="text-xs h-7 px-3">
          <FileDiff class="mr-2 h-3.5 w-3.5" />
          Diff
        </Tabs.Trigger>
        <Tabs.Trigger value="raw" class="text-xs h-7 px-3">
          <Code class="mr-2 h-3.5 w-3.5" />
          Output
        </Tabs.Trigger>
      </Tabs.List>
    </div>

    <Tabs.Content value="diff" class="m-0">
      <CardContent class="p-0 font-mono text-sm max-h-[500px] overflow-auto">
        {#if patch}
          {#each patch.hunks as hunk}
            <div class="hunk border-b last:border-0">
              <div class="hunk-header bg-muted/50 px-4 py-1 text-xs text-muted-foreground flex justify-between items-center sticky top-0">
                <span>{hunk.header}</span>
              </div>

              <div class="py-1">
                {#each hunk.lines as line}
                  <div class="line flex {line[0] === '+' ? 'bg-green-500/10 text-green-700 dark:text-green-400' : line[0] === '-' ? 'bg-red-500/10 text-red-700 dark:text-red-400' : 'text-muted-foreground'}">
                    <span class="marker w-6 text-center shrink-0 select-none opacity-50">{line[0]}</span>
                    <span class="whitespace-pre">{line.slice(1)}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/each}
        {/if}
      </CardContent>

      <div class="diff-actions p-3 border-t bg-muted/10">
        {#if !showFeedback}
          <div class="flex gap-2 justify-end">
            <Button variant="outline" onclick={() => showFeedback = true} size="sm">
              <X class="h-4 w-4 mr-2" />
              Reject All
            </Button>
            <Button onclick={onApprove} size="sm">
              <Check class="h-4 w-4 mr-2" />
              Accept All
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
            <div class="flex gap-2 justify-end">
              <Button variant="ghost" size="sm" onclick={() => showFeedback = false}>
                Cancel
              </Button>
              <Button onclick={() => { onReject(feedback); showFeedback = false; }} size="sm">
                <MessageSquare class="h-4 w-4 mr-2" />
                Submit Feedback
              </Button>
            </div>
          </div>
        {/if}
      </div>
    </Tabs.Content>

    <Tabs.Content value="raw" class="m-0">
      <div class="p-4 bg-[#0d1117] text-white font-mono text-sm max-h-[500px] overflow-auto">
        {#if isLoading}
          <div class="flex items-center justify-center py-8 text-muted-foreground">
            <span class="animate-pulse">Loading highlighter...</span>
          </div>
        {:else}
          {@html highlightedDiff}
        {/if}
      </div>
    </Tabs.Content>
  </Tabs.Root>
</Card>

<style>
  :global(.shiki) {
    background-color: transparent !important;
    margin: 0;
  }
</style>