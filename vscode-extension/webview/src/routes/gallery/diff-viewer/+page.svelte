<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import { ChevronDown, ChevronRight, FileCode, Info } from 'lucide-svelte';
	
	let diffExpanded1 = $state(true);
	let diffExpanded2 = $state(true);
	let diffExpanded3 = $state(true);
	let diffExpanded4 = $state(true);
	let diffExpanded5 = $state(true);
	
	// Mock parsed diff data
	const patch = {
		oldFileName: 'src/components/utils.ts',
		newFileName: 'src/components/utils.ts',
		hunks: [{
			oldStart: 1,
			oldLines: 8,
			newStart: 1,
			newLines: 13,
			lines: [
				' export function formatNumber(num: number) {',
				'-  return num.toLocaleString();',
				'+  return new Intl.NumberFormat("en-US").format(num);',
				' }',
				' ',
				' export function cn(...inputs: string[]) {',
				'   return inputs.filter(Boolean).join(" ");',
				'+}',
				'+',
				'+export function debounce(func: Function, wait: number) {',
				'+  let timeout: NodeJS.Timeout;',
				'+  return (...args: any[]) => clearTimeout(timeout) || (timeout = setTimeout(() => func(...args), wait));',
				' }'
			]
		}]
	};
	
	const additions = 6;
	const deletions = 1;
	const fileChanges = 1;
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-7xl mx-auto">
		<div class="mb-8">
			<h1 class="text-4xl font-bold mb-2">Diff Viewer Variations</h1>
			<p class="text-muted-foreground">
				Compare different styling options for the collapsible diff viewer
			</p>
		</div>

		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<!-- Variation 1: Current (Bright) -->
			<Card>
				<CardHeader>
					<CardTitle>Current - Bright Colors</CardTitle>
					<CardDescription>Original bright green/red color scheme</CardDescription>
				</CardHeader>
				<CardContent>
					<div class="diff-container">
						<Collapsible.Root bind:open={diffExpanded1}>
							<div class="rounded-lg border border-border bg-card overflow-hidden">
								<Collapsible.Trigger>
									{#snippet child({ props })}
										<button
											{...props}
											class="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
										>
											<div class="flex items-center gap-3">
												<div class="flex items-center gap-2">
													{#if diffExpanded1}
														<ChevronDown class="h-4 w-4 text-muted-foreground" />
													{:else}
														<ChevronRight class="h-4 w-4 text-muted-foreground" />
													{/if}
													<FileCode class="h-5 w-5 text-primary" />
												</div>
												<div class="flex flex-col items-start">
													<span class="font-mono text-sm font-semibold text-foreground">
														{patch.newFileName}
													</span>
													<span class="text-xs text-muted-foreground">
														Modified • {fileChanges} file{fileChanges !== 1 ? 's' : ''} changed
													</span>
												</div>
											</div>
											
											<div class="flex items-center gap-4">
												<div class="flex items-center gap-3 text-xs font-mono">
													<div class="flex items-center gap-1">
														<div class="w-2 h-2 rounded-full bg-green-500"></div>
														<span class="text-green-500 font-semibold">+{additions}</span>
													</div>
													<div class="flex items-center gap-1">
														<div class="w-2 h-2 rounded-full bg-red-500"></div>
														<span class="text-red-500 font-semibold">-{deletions}</span>
													</div>
												</div>
												
												<div class="h-2 w-32 rounded-full overflow-hidden bg-muted flex">
													<div
														class="bg-green-500 transition-all"
														style="width: {additions / (additions + deletions) * 100}%"
													></div>
													<div
														class="bg-red-500 transition-all"
														style="width: {deletions / (additions + deletions) * 100}%"
													></div>
												</div>
											</div>
										</button>
									{/snippet}
								</Collapsible.Trigger>

								<Collapsible.Content>
									<div class="border-t border-border">
										<div class="bg-muted/20 font-mono text-xs max-h-96 overflow-auto">
											{#if patch}
												{#each patch.hunks as hunk}
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

										<div class="px-4 py-3 bg-card border-t border-border flex items-center gap-2">
											<Badge variant="outline" class="text-xs">
												<FileCode class="h-3 w-3 mr-1" />
												TypeScript
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
				</CardContent>
			</Card>

			<!-- Variation 2: Muted Colors -->
			<Card>
				<CardHeader>
					<CardTitle>Muted Colors</CardTitle>
					<CardDescription>Softer green-600/red-600 with 60% opacity</CardDescription>
				</CardHeader>
				<CardContent>
					<div class="diff-container">
						<Collapsible.Root bind:open={diffExpanded2}>
							<div class="rounded-lg border border-border bg-card overflow-hidden">
								<Collapsible.Trigger>
									{#snippet child({ props })}
										<button
											{...props}
											class="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
										>
											<div class="flex items-center gap-3">
												<div class="flex items-center gap-2">
													{#if diffExpanded2}
														<ChevronDown class="h-4 w-4 text-muted-foreground" />
													{:else}
														<ChevronRight class="h-4 w-4 text-muted-foreground" />
													{/if}
													<FileCode class="h-5 w-5 text-primary" />
												</div>
												<div class="flex flex-col items-start">
													<span class="font-mono text-sm font-semibold text-foreground">
														{patch.newFileName}
													</span>
													<span class="text-xs text-muted-foreground">
														Modified • {fileChanges} file{fileChanges !== 1 ? 's' : ''} changed
													</span>
												</div>
											</div>
											
											<div class="flex items-center gap-4">
												<div class="flex items-center gap-3 text-xs font-mono">
													<div class="flex items-center gap-1">
														<div class="w-2 h-2 rounded-full bg-green-600/60"></div>
														<span class="text-green-600/80 font-semibold">+{additions}</span>
													</div>
													<div class="flex items-center gap-1">
														<div class="w-2 h-2 rounded-full bg-red-600/60"></div>
														<span class="text-red-600/80 font-semibold">-{deletions}</span>
													</div>
												</div>
												
												<div class="h-2 w-32 rounded-full overflow-hidden bg-muted flex">
													<div class="bg-green-600/60 transition-all" style="width: {additions / (additions + deletions) * 100}%"></div>
													<div class="bg-red-600/60 transition-all" style="width: {deletions / (additions + deletions) * 100}%"></div>
												</div>
											</div>
										</button>
									{/snippet}
								</Collapsible.Trigger>

								<Collapsible.Content>
									<div class="border-t border-border">
										<div class="bg-muted/20 font-mono text-xs max-h-96 overflow-auto">
											{#if patch}
												{#each patch.hunks as hunk}
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

										<div class="px-4 py-3 bg-card border-t border-border flex items-center gap-2">
											<Badge variant="outline" class="text-xs">
												<FileCode class="h-3 w-3 mr-1" />
												TypeScript
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
				</CardContent>
			</Card>

			<!-- Variation 3: Subtle with Border -->
			<Card>
				<CardHeader>
					<CardTitle>Subtle with Border</CardTitle>
					<CardDescription>Emerald/rose with borders and lower opacity</CardDescription>
				</CardHeader>
				<CardContent>
					<div class="diff-container">
						<Collapsible.Root bind:open={diffExpanded3}>
							<div class="rounded-lg border border-border bg-card overflow-hidden">
								<Collapsible.Trigger>
									{#snippet child({ props })}
										<button
											{...props}
											class="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
										>
											<div class="flex items-center gap-3">
												<div class="flex items-center gap-2">
													{#if diffExpanded3}
														<ChevronDown class="h-4 w-4 text-muted-foreground" />
													{:else}
														<ChevronRight class="h-4 w-4 text-muted-foreground" />
													{/if}
													<FileCode class="h-5 w-5 text-primary" />
												</div>
												<div class="flex flex-col items-start">
													<span class="font-mono text-sm font-semibold text-foreground">
														{patch.newFileName}
													</span>
													<span class="text-xs text-muted-foreground">
														Modified • {fileChanges} file{fileChanges !== 1 ? 's' : ''} changed
													</span>
												</div>
											</div>
											
											<div class="flex items-center gap-4">
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
										<div class="bg-muted/20 font-mono text-xs max-h-96 overflow-auto">
											{#if patch}
												{#each patch.hunks as hunk}
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

										<div class="px-4 py-3 bg-card border-t border-border flex items-center gap-2">
											<Badge variant="outline" class="text-xs">
												<FileCode class="h-3 w-3 mr-1" />
												TypeScript
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
				</CardContent>
			</Card>

			<!-- Variation 4: Very Subtle -->
			<Card>
				<CardHeader>
					<CardTitle>Very Subtle - Foreground Based</CardTitle>
					<CardDescription>Minimal color with muted-foreground text</CardDescription>
				</CardHeader>
				<CardContent>
					<div class="diff-container">
						<Collapsible.Root bind:open={diffExpanded4}>
							<div class="rounded-lg border border-border bg-card overflow-hidden">
								<Collapsible.Trigger>
									{#snippet child({ props })}
										<button
											{...props}
											class="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
										>
											<div class="flex items-center gap-3">
												<div class="flex items-center gap-2">
													{#if diffExpanded4}
														<ChevronDown class="h-4 w-4 text-muted-foreground" />
													{:else}
														<ChevronRight class="h-4 w-4 text-muted-foreground" />
													{/if}
													<FileCode class="h-5 w-5 text-primary" />
												</div>
												<div class="flex flex-col items-start">
													<span class="font-mono text-sm font-semibold text-foreground">
														{patch.newFileName}
													</span>
													<span class="text-xs text-muted-foreground">
														Modified • {fileChanges} file{fileChanges !== 1 ? 's' : ''} changed
													</span>
												</div>
											</div>
											
											<div class="flex items-center gap-4">
												<div class="flex items-center gap-3 text-xs font-mono text-muted-foreground">
													<div class="flex items-center gap-1">
														<div class="w-2 h-2 rounded-full bg-green-700/40 dark:bg-green-500/30"></div>
														<span class="font-semibold">+{additions}</span>
													</div>
													<div class="flex items-center gap-1">
														<div class="w-2 h-2 rounded-full bg-red-700/40 dark:bg-red-500/30"></div>
														<span class="font-semibold">-{deletions}</span>
													</div>
												</div>
												
												<div class="h-2 w-32 rounded-full overflow-hidden bg-muted/50 flex">
													<div class="bg-green-700/30 dark:bg-green-500/25 transition-all" style="width: {additions / (additions + deletions) * 100}%"></div>
													<div class="bg-red-700/30 dark:bg-red-500/25 transition-all" style="width: {deletions / (additions + deletions) * 100}%"></div>
												</div>
											</div>
										</button>
									{/snippet}
								</Collapsible.Trigger>

								<Collapsible.Content>
									<div class="border-t border-border">
										<div class="bg-muted/20 font-mono text-xs max-h-96 overflow-auto">
											{#if patch}
												{#each patch.hunks as hunk}
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

										<div class="px-4 py-3 bg-card border-t border-border flex items-center gap-2">
											<Badge variant="outline" class="text-xs">
												<FileCode class="h-3 w-3 mr-1" />
												TypeScript
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
				</CardContent>
			</Card>

			<!-- Variation 5: Minimal Dots -->
			<Card>
				<CardHeader>
					<CardTitle>Minimal - Dots Only</CardTitle>
					<CardDescription>Individual dots instead of progress bar</CardDescription>
				</CardHeader>
				<CardContent>
					<div class="diff-container">
						<Collapsible.Root bind:open={diffExpanded5}>
							<div class="rounded-lg border border-border bg-card overflow-hidden">
								<Collapsible.Trigger>
									{#snippet child({ props })}
										<button
											{...props}
											class="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
										>
											<div class="flex items-center gap-3">
												<div class="flex items-center gap-2">
													{#if diffExpanded5}
														<ChevronDown class="h-4 w-4 text-muted-foreground" />
													{:else}
														<ChevronRight class="h-4 w-4 text-muted-foreground" />
													{/if}
													<FileCode class="h-5 w-5 text-primary" />
												</div>
												<div class="flex flex-col items-start">
													<span class="font-mono text-sm font-semibold text-foreground">
														{patch.newFileName}
													</span>
													<span class="text-xs text-muted-foreground">
														Modified • {fileChanges} file{fileChanges !== 1 ? 's' : ''} changed
													</span>
												</div>
											</div>
											
											<div class="flex items-center gap-4">
												<div class="flex items-center gap-3 text-xs font-mono text-muted-foreground">
													<div class="flex items-center gap-1">
														<span class="font-semibold">+{additions}</span>
													</div>
													<div class="flex items-center gap-1">
														<span class="font-semibold">-{deletions}</span>
													</div>
												</div>
												
												<div class="flex items-center gap-0.5">
													{#each Array(additions) as _, i}
														<div class="w-1 h-1 rounded-sm bg-green-600/50"></div>
													{/each}
													{#each Array(deletions) as _, i}
														<div class="w-1 h-1 rounded-sm bg-red-600/50"></div>
													{/each}
												</div>
											</div>
										</button>
									{/snippet}
								</Collapsible.Trigger>

								<Collapsible.Content>
									<div class="border-t border-border">
										<div class="bg-muted/20 font-mono text-xs max-h-96 overflow-auto">
											{#if patch}
												{#each patch.hunks as hunk}
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

										<div class="px-4 py-3 bg-card border-t border-border flex items-center gap-2">
											<Badge variant="outline" class="text-xs">
												<FileCode class="h-3 w-3 mr-1" />
												TypeScript
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
				</CardContent>
			</Card>
		</div>
	</div>
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