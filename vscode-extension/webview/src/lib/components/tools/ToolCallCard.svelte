<!-- src/lib/components/tools/ToolCallCard.svelte -->
<script lang="ts">
	import { Card, CardHeader, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Check from '@lucide/svelte/icons/check';
	import X from '@lucide/svelte/icons/x';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import { slide } from 'svelte/transition';
	import DiffViewer from './DiffViewer.svelte';
	import type { FileDiff } from '../../../../../shared/types/events';

	export let tool: string;
	export let input: Record<string, any>;
	export let result: Record<string, any> | null = null;
	export let error: string | null = null;
	export let status: 'running' | 'success' | 'error' = 'running';
	export let executionTime: number | null = null;
	export let collapsed = true;
	export let diff: FileDiff | undefined = undefined;

	let expanded = !collapsed;
	
	// Detect if this is a file editing tool
	const isFileEditTool = ['apply_diff', 'write_to_file', 'file_write', 'search_and_replace', 'insert_content'].includes(tool);

	const toolIcons: Record<string, string> = {
		search_knowledge: '🔍',
		kb_search: '🔍',
		read_files: '📄',
		file_write: '✍️',
		apply_diff: '🔧',
		run_command: '⚡',
		fetch_chunk: '📦',
		fetch_lines: '📝'
	};

	function toggleExpanded() {
		expanded = !expanded;
	}

	function handleKeypress(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			toggleExpanded();
		}
	}
</script>

<Card class="tool-call-card mb-2 py-2 gap-0" data-status={status}>
	<CardHeader
		class="cursor-pointer hover:bg-muted/50 !py-2 !px-2 transition-colors"
		onclick={toggleExpanded}
		onkeypress={handleKeypress}
		role="button"
		tabindex="0"
		aria-expanded={expanded}
		data-status={status}
	>
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-3 flex-1 min-w-0">
				{#if expanded}
					<ChevronDown class="h-4 w-4 shrink-0" />
				{:else}
					<ChevronRight class="h-4 w-4 shrink-0" />
				{/if}

				<span class="text-2xl shrink-0">{toolIcons[tool] || '🔨'}</span>
				<div class="font-mono text-sm truncate">{tool}</div>
			</div>

			<div class="flex items-center gap-2 shrink-0">
				{#if executionTime}
					<Badge variant="outline" class="text-xs">{executionTime}ms</Badge>
				{/if}

				{#if status === 'running'}
					<Loader2 class="h-4 w-4 animate-spin text-blue-500" />
				{:else if status === 'success'}
					<Check class="h-4 w-4 text-green-500" />
				{:else}
					<X class="h-4 w-4 text-red-500" />
				{/if}
			</div>
		</div>
	</CardHeader>

	{#if expanded}
		<div transition:slide={{ duration: 200 }}>
			<CardContent class="!px-2 !pb-2 !pt-0">
				<div class="space-y-2">
					<!-- Show diff viewer for file editing tools if diff data is available -->
					{#if isFileEditTool && diff}
						<div class="mb-2">
							<DiffViewer {diff} defaultExpanded={true} />
						</div>
					{/if}
					
					<div>
						<div class="text-xs font-semibold mb-0.5 text-muted-foreground">Input</div>
						<pre
							class="text-xs bg-muted p-1.5 rounded overflow-x-auto">{JSON.stringify(
								input,
								null,
								2
							)}</pre>
					</div>

					{#if error}
						<div class="bg-destructive/10 p-1.5 rounded text-xs text-destructive">
							{error}
						</div>
					{:else if result}
						<div>
							<div class="text-xs font-semibold mb-0.5 text-muted-foreground">Result</div>
							<pre
								class="text-xs bg-muted p-1.5 rounded overflow-x-auto">{JSON.stringify(
									result,
									null,
									2
								)}</pre>
						</div>
					{/if}
				</div>
			</CardContent>
		</div>
	{/if}
</Card>

<style>
	:global(.tool-call-card) {
		border-left: 2px solid hsl(var(--border));
	}

	:global(.tool-call-card[data-status='running']) {
		border-left-color: hsl(var(--primary));
	}

	:global(.tool-call-card[data-status='success']) {
		border-left-color: rgb(34, 197, 94);
	}

	:global(.tool-call-card[data-status='error']) {
		border-left-color: rgb(239, 68, 68);
	}
</style>