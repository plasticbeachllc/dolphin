<script lang="ts">
	import * as Sheet from '$lib/components/ui/sheet';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { ChevronDown, Target, Brain, GitBranch, CheckSquare, X } from 'lucide-svelte';
	
	interface ReasoningChain {
		step: string;
		reasoning: string;
		confidence: number;
	}
	
	interface Alternative {
		approach: string;
		pros: string[];
		cons: string[];
		whyNotChosen: string;
	}
	
	interface Props {
		currentGoal: string;
		reasoningChain: ReasoningChain[];
		alternatives: Alternative[];
		successCriteria: string[];
		open: boolean;
		onClose?: () => void;
	}
	
	let {
		currentGoal,
		reasoningChain,
		alternatives,
		successCriteria,
		open = $bindable(),
		onClose
	}: Props = $props();
	
	let alternativesExpanded = $state(false);
	let checkedCriteria = $state<Record<number, boolean>>({});
	
	function handleClose() {
		open = false;
		onClose?.();
	}
	
	function getConfidenceColor(confidence: number) {
		if (confidence >= 0.8) return 'bg-green-500';
		if (confidence >= 0.6) return 'bg-yellow-500';
		return 'bg-orange-500';
	}
</script>

<Sheet.Root bind:open>
	<Sheet.Content side="right" class="w-full sm:max-w-[540px] overflow-y-auto">
		<Sheet.Header>
			<div class="flex items-start justify-between">
				<div class="flex-1">
					<div class="flex items-center gap-2 mb-2">
						<Target class="size-5 text-primary" />
						<Sheet.Title>Goal Context</Sheet.Title>
					</div>
					<Sheet.Description>{currentGoal}</Sheet.Description>
				</div>
				<Button size="icon" variant="ghost" onclick={handleClose}>
					<X class="size-4" />
				</Button>
			</div>
		</Sheet.Header>
		
		<div class="space-y-6 py-6">
			<!-- Reasoning Chain Section -->
			<section class="space-y-4">
				<div class="flex items-center gap-2">
					<Brain class="size-4 text-primary" />
					<h3 class="text-sm font-semibold">Reasoning Chain</h3>
				</div>
				
				<div class="space-y-3">
					{#each reasoningChain as reason, i}
						<div class="relative pl-6 pb-3 last:pb-0">
							<!-- Connector line -->
							{#if i < reasoningChain.length - 1}
								<div class="absolute left-[11px] top-8 w-0.5 h-full bg-border"></div>
							{/if}
							
							<div class="flex gap-3">
								<!-- Step number badge -->
								<Badge
									variant="outline"
									class="absolute left-0 top-0 size-6 flex items-center justify-center p-0 text-xs"
								>
									{i + 1}
								</Badge>
								
								<div class="flex-1 space-y-2">
									<p class="text-sm font-medium">{reason.step}</p>
									<p class="text-xs text-muted-foreground">{reason.reasoning}</p>
									
									<!-- Confidence bar -->
									<div class="space-y-1">
										<div class="flex items-center justify-between text-xs">
											<span class="text-muted-foreground">Confidence</span>
											<span class="font-semibold">{Math.round(reason.confidence * 100)}%</span>
										</div>
										<div class="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
											<div
												class="h-full {getConfidenceColor(reason.confidence)} transition-all duration-500"
												style="width: {reason.confidence * 100}%"
											></div>
										</div>
									</div>
								</div>
							</div>
						</div>
					{/each}
				</div>
			</section>
			
			<div class="h-px bg-border"></div>
			
			<!-- Alternative Approaches Section -->
			<section class="space-y-4">
				<button
					class="w-full flex items-center justify-between text-left group"
					onclick={() => alternativesExpanded = !alternativesExpanded}
				>
					<div class="flex items-center gap-2">
						<GitBranch class="size-4 text-primary" />
						<h3 class="text-sm font-semibold">Alternative Approaches</h3>
						<Badge variant="secondary" class="text-xs">{alternatives.length}</Badge>
					</div>
					<ChevronDown
						class="size-4 text-muted-foreground transition-transform duration-200 {alternativesExpanded ? 'rotate-180' : ''}"
					/>
				</button>
				
				{#if alternativesExpanded}
					<div class="space-y-3 animate-fade-in">
						{#each alternatives as alt}
							<Card.Root class="opacity-80 hover:opacity-100 transition-opacity">
								<Card.Header class="pb-3">
									<Card.Title class="text-sm">{alt.approach}</Card.Title>
								</Card.Header>
								<Card.Content class="space-y-3 text-xs">
									<!-- Pros -->
									<div class="space-y-1">
										<p class="font-semibold text-green-600 dark:text-green-400">Pros:</p>
										<ul class="list-disc list-inside space-y-0.5 text-muted-foreground">
											{#each alt.pros as pro}
												<li>{pro}</li>
											{/each}
										</ul>
									</div>
									
									<!-- Cons -->
									<div class="space-y-1">
										<p class="font-semibold text-red-600 dark:text-red-400">Cons:</p>
										<ul class="list-disc list-inside space-y-0.5 text-muted-foreground">
											{#each alt.cons as con}
												<li>{con}</li>
											{/each}
										</ul>
									</div>
									
									<!-- Why not chosen -->
									<div class="pt-2 border-t border-border">
										<p class="italic text-muted-foreground">
											<strong class="font-semibold not-italic">Why not:</strong> {alt.whyNotChosen}
										</p>
									</div>
								</Card.Content>
							</Card.Root>
						{/each}
					</div>
				{/if}
			</section>
			
			<div class="h-px bg-border"></div>
			
			<!-- Success Criteria Section -->
			<section class="space-y-4">
				<div class="flex items-center gap-2">
					<CheckSquare class="size-4 text-primary" />
					<h3 class="text-sm font-semibold">Success Criteria</h3>
					<Badge variant="outline" class="text-xs">
						{Object.values(checkedCriteria).filter(Boolean).length}/{successCriteria.length}
					</Badge>
				</div>
				
				<div class="space-y-3">
					{#each successCriteria as criterion, i}
						<div class="flex items-start gap-3">
							<Checkbox
								id="criterion-{i}"
								bind:checked={checkedCriteria[i]}
								class="mt-0.5"
							/>
							<label
								for="criterion-{i}"
								class="text-sm leading-relaxed cursor-pointer select-none"
								class:text-muted-foreground={checkedCriteria[i]}
								class:line-through={checkedCriteria[i]}
							>
								{criterion}
							</label>
						</div>
					{/each}
				</div>
			</section>
			
			<!-- Info Footer -->
			<div class="pt-4 border-t border-border">
				<div class="flex items-start gap-2 text-xs text-muted-foreground">
					<div class="size-4 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
						<span class="text-[10px]">💡</span>
					</div>
					<p>
						This panel shows the agent's decision-making process, providing transparency into the reasoning behind the chosen approach.
					</p>
				</div>
			</div>
		</div>
	</Sheet.Content>
</Sheet.Root>

<style>
	/* Smooth fade-in animation for collapsible content */
	@keyframes fade-in {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	
	.animate-fade-in {
		animation: fade-in 200ms ease-out;
	}
</style>