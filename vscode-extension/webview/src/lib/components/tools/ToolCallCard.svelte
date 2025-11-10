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

	// Extract file path from input for peek action
	function getFilePath(): string | null {
		if (!input) return null;
		return input.file_path || input.path || input.filename || null;
	}

	function handlePeekFile(e: Event) {
		e.stopPropagation();
		const filePath = getFilePath();
		if (filePath) {
			// TODO: Send message to extension to open file
			console.log('[ToolCallCard] Peek file:', filePath);
		}
	}

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

	// Human-readable tool names for better accessibility
	const toolNames: Record<string, string> = {
		search_knowledge: 'Search Knowledge Base',
		kb_search: 'Knowledge Base Search',
		read_files: 'Read Files',
		file_write: 'Write File',
		apply_diff: 'Apply Diff',
		run_command: 'Run Command',
		fetch_chunk: 'Fetch Chunk',
		fetch_lines: 'Fetch Lines'
	};

	const toolName = toolNames[tool] || tool.replace(/_/g, ' ');
</script>

<Card class="tool-call-card mb-2 py-2 gap-0" data-status={status} role="region" aria-label="{toolName} tool call">
	<CardHeader
		class="cursor-pointer hover:bg-muted/50 !py-2 !px-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
		onclick={toggleExpanded}
		onkeypress={handleKeypress}
		role="button"
		tabindex="0"
		aria-expanded={expanded}
		aria-label="{expanded ? 'Collapse' : 'Expand'} {toolName} details. Status: {status}. {executionTime ? `Execution time: ${executionTime} milliseconds.` : ''}"
		data-status={status}
	>
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-3 flex-1 min-w-0">
				{#if expanded}
					<ChevronDown class="h-4 w-4 shrink-0" aria-hidden="true" />
				{:else}
					<ChevronRight class="h-4 w-4 shrink-0" aria-hidden="true" />
				{/if}

				<span class="text-2xl shrink-0" aria-hidden="true">{toolIcons[tool] || '🔨'}</span>
				<div class="font-mono text-sm truncate">{tool}</div>
			</div>

			<div class="flex items-center gap-2 shrink-0">
				{#if isFileEditTool && getFilePath() && status === 'success'}
					<button
						class="peek-button text-xs"
						onclick={handlePeekFile}
						aria-label="View file {getFilePath()}"
						title="View file"
					>
						👁️ View
					</button>
				{/if}

				{#if executionTime}
					<Badge variant="outline" class="text-xs" aria-label="Execution time: {executionTime} milliseconds">{executionTime}ms</Badge>
				{/if}

				{#if status === 'running'}
					<Loader2 class="h-4 w-4 animate-spin tool-status-running" aria-label="Running" />
				{:else if status === 'success'}
					<Check class="h-4 w-4 tool-status-success" aria-label="Success" />
				{:else}
					<X class="h-4 w-4 tool-status-error" aria-label="Error" />
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
		border-left-color: var(--vscode-charts-blue, hsl(var(--primary)));
	}

	:global(.tool-call-card[data-status='success']) {
		border-left-color: var(--vscode-charts-green, hsl(142 76% 36%));
	}

	:global(.tool-call-card[data-status='error']) {
		border-left-color: var(--vscode-charts-red, hsl(0 84% 60%));
	}

	/* Theme-aware status icon colors */
	:global(.tool-status-running) {
		color: var(--vscode-charts-blue, hsl(var(--primary)));
	}

	:global(.tool-status-success) {
		color: var(--vscode-charts-green, hsl(142 76% 36%));
	}

	:global(.tool-status-error) {
		color: var(--vscode-charts-red, hsl(0 84% 60%));
	}

	.peek-button {
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		background: var(--vscode-input-background, hsl(var(--muted)));
		color: var(--vscode-foreground, hsl(var(--foreground)));
		border: 1px solid var(--vscode-input-border, hsl(var(--border)));
		cursor: pointer;
		transition: all 0.2s;
		font-family: inherit;
	}

	.peek-button:hover {
		background: var(--vscode-button-hoverBackground, hsl(var(--accent)));
		border-color: var(--vscode-focusBorder, hsl(var(--primary)));
	}

	.peek-button:focus-visible {
		outline: 2px solid var(--vscode-focusBorder, hsl(var(--primary)));
		outline-offset: 2px;
	}
</style>