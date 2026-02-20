<script lang="ts">
	import * as Accordion from '$lib/components/ui/accordion';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Play, Clock, CheckCircle2, Circle, Loader2, AlertTriangle } from 'lucide-svelte';
	import { Chart, Svg, Rect } from 'layerchart';
	import { scaleLinear } from 'd3-scale';

	interface PlanStep {
		id: string;
		description: string;
		status: 'pending' | 'running' | 'completed' | 'error';
		estimatedTime?: number;
		actualTime?: number;
		context?: string;
	}

	interface PlanPhase {
		id: string;
		name: string;
		status: 'pending' | 'active' | 'completed';
		steps: PlanStep[];
	}

	interface Props {
		phases: PlanPhase[];
	}

	let { phases }: Props = $props();

	// Status colors
	const statusColors = {
		pending: 'text-muted-foreground',
		running: 'text-blue-500',
		completed: 'text-green-500',
		error: 'text-red-500'
	};

	const statusBgColors = {
		pending: 'bg-muted',
		running: 'bg-blue-500',
		completed: 'bg-green-500',
		error: 'bg-red-500'
	};

	function formatDuration(ms: number) {
		const seconds = Math.floor(ms / 1000);
		const minutes = Math.floor(seconds / 60);
		const remainingSeconds = seconds % 60;

		if (minutes > 0) {
			return `${minutes}m ${remainingSeconds}s`;
		}
		return `${seconds}s`;
	}

	function getPhaseProgress(phase: PlanPhase) {
		const completed = phase.steps.filter(s => s.status === 'completed').length;
		return { completed, total: phase.steps.length };
	}

	function isTimeOverestimated(estimated?: number, actual?: number) {
		if (!estimated || !actual) return false;
		return actual > estimated;
	}
</script>

<div class="enhanced-timeline w-full">
<div class="enhanced-timeline w-full">
	<Accordion.Root type="multiple" class="w-full space-y-2">
		{#each phases as phase}
			{@const progress = getPhaseProgress(phase)}
			<Accordion.Item value={phase.id} class="border rounded-lg">
				<Accordion.Trigger class="hover:no-underline flex w-full items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors rounded-lg">
					<div class="flex items-center gap-3">
						<!-- Phase Status Icon -->
						{#if phase.status === 'completed'}
							<CheckCircle2 class="size-5 text-green-500" />
						{:else if phase.status === 'active'}
							<Loader2 class="size-5 text-blue-500 animate-spin" />
						{:else}
							<Circle class="size-5 text-muted-foreground" />
						{/if}

						<!-- Phase Name and Progress -->
						<div class="flex items-center gap-3">
							<Badge
								variant={phase.status === 'completed' ? 'secondary' : phase.status === 'active' ? 'default' : 'outline'}
								class="text-sm font-semibold"
							>
								{phase.name}
							</Badge>
							<span class="text-sm text-muted-foreground">
								{progress.completed}/{progress.total} steps
							</span>
						</div>
					</div>

					<!-- Progress Bar -->
					<div class="flex items-center gap-3">
						<div class="h-2 w-32 bg-secondary rounded-full overflow-hidden relative">
							<Chart
								data={[{ value: progress.completed }]}
								x="value"
								xDomain={[0, Math.max(progress.total, 1)]}
								xScale={scaleLinear()}
								padding={{ top: 0, bottom: 0, left: 0, right: 0 }}
								let:xScale
								let:height
							>
								<Svg>
									<Rect
										x={0}
										y={0}
										width={xScale(progress.completed)}
										height={height}
										class="fill-primary transition-all duration-500"
									/>
								</Svg>
							</Chart>
						</div>
					</div>
				</Accordion.Trigger>

				<Accordion.Content>
					<!-- Interior panel with proper padding -->
					<div class="p-6 bg-muted/20 border-t">
						<!-- Timeline Track -->
						<div class="relative pl-8">
							{#each phase.steps as step, i}
								<div class="relative pb-8 last:pb-0">
									<!-- Step Node -->
									<div class="flex items-start gap-4">
										<!-- Status Circle -->
										<div
											class="relative size-3 rounded-full border-2 border-background {statusBgColors[step.status]} shrink-0"
											class:animate-pulse={step.status === 'running'}
											style="margin-top: 2px;"
										></div>

										<!-- Connector Line -->
										{#if i < phase.steps.length - 1}
											<div
												class="absolute left-[5px] top-2 w-0.5 h-[calc(100%-8px)] {step.status === 'completed' ? 'bg-green-500' : 'bg-border'}"
											></div>
										{/if}

										<!-- Step Content -->
										<div class="flex-1 space-y-2">
											<div class="flex items-center justify-between">
												<div class="flex items-center gap-2">
													<span class="text-sm font-medium {statusColors[step.status]}">
														{step.description}
													</span>
													{#if step.status === 'running'}
														<Badge variant="secondary" class="text-xs">
															In Progress
														</Badge>
													{/if}
												</div>
											</div>

											<!-- Context -->
											{#if step.context}
												<p class="text-xs text-muted-foreground italic">
													{step.context}
												</p>
											{/if}

											<!-- Time Comparison -->
											{#if step.estimatedTime && step.actualTime}
												{@const isOver = isTimeOverestimated(step.estimatedTime, step.actualTime)}
												<div class="flex items-center gap-1.5 text-xs mt-1 {isOver ? 'text-red-500' : 'text-muted-foreground'}">
													{#if isOver}
														<AlertTriangle class="size-3" />
													{:else}
														<Clock class="size-3" />
													{/if}
													<span class="font-mono">
														{formatDuration(step.actualTime)}
													</span>
													<span class="text-muted-foreground/50">/</span>
													<span class="text-muted-foreground">
														{formatDuration(step.estimatedTime)}
													</span>
												</div>
											{/if}
										</div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				</Accordion.Content>
			</Accordion.Item>
		{/each}
	</Accordion.Root>
</div>
</div>

<style>
	/* Add smooth transitions for accordion animations */
	:global(.enhanced-timeline [data-accordion-content]) {
		transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
	}
</style>