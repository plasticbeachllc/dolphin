<script lang="ts">
	import * as Collapsible from '$lib/components/ui/collapsible';
	import { Badge } from '$lib/components/ui/badge';
	import { ChevronDown, ChevronRight, FileCode } from 'lucide-svelte';
	
	interface DiffHunk {
		oldStart: number;
		oldLines: number;
		newStart: number;
		newLines: number;
		lines: string[];
	}
	
	interface FileDiff {
		oldFileName: string;
		newFileName: string;
		additions: number;
		deletions: number;
		hunks: DiffHunk[];
	}
	
	interface Props {
		diff: FileDiff;
		defaultExpanded?: boolean;
	}
	
	let { diff, defaultExpanded = true }: Props = $props();
	
	let expanded = $state(defaultExpanded);
	
	const additions = diff.additions;
	const deletions = diff.deletions;
	const fileChanges = 1;
</script>

<div class="diff-container">
	<Collapsible.Root bind:open={expanded}>
		<div class="rounded-lg border border-border bg-card overflow-hidden">
			<Collapsible.Trigger>
				{#snippet child({ props })}
					<button
						{...props}
						class="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
					>
						<div class="flex items-center gap-3">
							<div class="flex items-center gap-2">
								{#if expanded}
									<ChevronDown class="h-4 w-4 text-muted-foreground" />
								{:else}
									<ChevronRight class="h-4 w-4 text-muted-foreground" />
								{/if}
								<FileCode class="h-5 w-5 text-primary" />
							</div>
							<div class="flex flex-col items-start">
								<span class="font-mono text-sm font-semibold text-foreground">
									{diff.newFileName}
								</span>
								<span class="text-xs text-muted-foreground">
									Modified • {fileChanges} file{fileChanges !== 1 ? 's' : ''} changed
								</span>
							</div>
						</div>
						
						<div class="flex items-center gap-4">
							<!-- Diff Stats -->
							<div class="flex items-center gap-3 text-xs font-mono">
								<div class="flex items-center gap-1">
									<div class="w-2 h-2 rounded-full bg-emerald-500/40 border border-emerald-500/60"></div>
									<span class="text-emerald-600 dark:text-emerald-400 font-semibold">+{additions}</span>
								</div>
								<div class="flex items-center gap-1">
									<div class="w-2 h-2 rounded-full bg-rose-500/40 border border-rose-500/60"></div>
									<span class="text-rose-600 dark:text-rose-400 font-semibold">-{deletions}</span>
								</div>
							</div>
							
							<!-- Visual diff bar -->
							<div class="h-2 w-32 rounded-full overflow-hidden border border-border bg-background flex">
								<div class="bg-emerald-500/50 transition-all" style="width: {additions / (additions + deletions) * 100}%"></div>
								<div class="bg-rose-500/50 transition-all" style="width: {deletions / (additions + deletions) * 100}%"></div>
							</div>
						</div>
					</button>
				{/snippet}
			</Collapsible.Trigger>

			<Collapsible.Content>
				<div class="border-t border-border">
					<!-- Diff Content -->
					<div class="bg-muted/20 font-mono text-xs max-h-96 overflow-auto">
						{#if diff}
							{#each diff.hunks as hunk}
								<div class="hunk">
									<div class="sticky top-0 px-4 py-1.5 bg-primary/10 border-y border-border/50 text-primary font-semibold">
										@@ -{hunk.oldStart},{hunk.oldLines} +{hunk.newStart},{hunk.newLines} @@
									</div>
									
									{#each hunk.lines as line, lineIdx}
										{@const lineType = line[0] === '+' ? 'add' : line[0] === '-' ? 'del' : 'ctx'}
										<div class="diff-line {lineType}">
											<div class="line-numbers select-none flex">
												<span class="line-num old-line {lineType === 'add' ? 'opacity-30' : ''}">
													{lineType !== 'add' ? (hunk.oldStart + lineIdx) : ''}
												</span>
												<span class="line-num new-line {lineType === 'del' ? 'opacity-30' : ''}">
													{lineType !== 'del' ? (hunk.newStart + lineIdx) : ''}
												</span>
											</div>
											
											<span class="marker select-none font-bold">
												{line[0]}
											</span>
											
											<span class="code-content flex-1">
												{line.slice(1)}
											</span>
										</div>
									{/each}
								</div>
							{/each}
						{/if}
					</div>

					<!-- Metadata Footer -->
					<div class="px-4 py-3 bg-card border-t border-border flex items-center gap-2">
						<Badge variant="outline" class="text-xs">
							<FileCode class="h-3 w-3 mr-1" />
							{diff.newFileName.split('.').pop()?.toUpperCase() || 'File'}
						</Badge>
						<Badge variant="outline" class="text-xs">
							{additions + deletions} lines changed
						</Badge>
					</div>
				</div>
			</Collapsible.Content>
		</div>
	</Collapsible.Root>
</div>

<style>
	.diff-line {
		display: flex;
		align-items: center;
		padding: 0.125rem 1rem;
		line-height: 1.5;
		min-height: 1.5rem;
	}
	
	.diff-line.add {
		background: rgba(34, 197, 94, 0.12);
	}
	
	.diff-line.add .marker {
		color: rgb(34, 197, 94);
	}
	
	.diff-line.del {
		background: rgba(239, 68, 68, 0.12);
	}
	
	.diff-line.del .marker {
		color: rgb(239, 68, 68);
	}
	
	.diff-line.ctx {
		color: var(--foreground);
		opacity: 0.8;
	}
	
	.line-numbers {
		display: flex;
		gap: 0.75rem;
		margin-right: 1rem;
		min-width: 4rem;
	}
	
	.line-num {
		display: inline-block;
		width: 2rem;
		text-align: right;
		color: var(--muted-foreground);
		user-select: none;
	}
	
	.marker {
		display: inline-block;
		width: 1ch;
		margin-right: 1ch;
		text-align: center;
	}
	
	.code-content {
		white-space: pre;
		overflow-x: auto;
	}
	
	/* Scrollbar styling */
	.diff-container ::-webkit-scrollbar {
		width: 8px;
		height: 8px;
	}
	
	.diff-container ::-webkit-scrollbar-track {
		background: var(--muted);
		border-radius: 4px;
	}
	
	.diff-container ::-webkit-scrollbar-thumb {
		background: var(--muted-foreground);
		border-radius: 4px;
	}
	
	.diff-container ::-webkit-scrollbar-thumb:hover {
		background: var(--foreground);
	}
</style>