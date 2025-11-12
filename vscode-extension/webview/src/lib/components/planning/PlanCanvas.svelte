<script lang="ts">
	import { onMount } from 'svelte';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import * as Popover from '$lib/components/ui/popover';
	import { ZoomIn, ZoomOut, Maximize2, Info } from 'lucide-svelte';
	
	interface PlanNode {
		id: string;
		type: 'goal' | 'step' | 'action' | 'tool';
		label: string;
		status: 'pending' | 'active' | 'completed' | 'error';
		x: number;
		y: number;
		children: string[];
		progress?: number;
		metadata?: any;
	}
	
	interface Edge {
		from: string;
		to: string;
	}
	
	interface Props {
		nodes: PlanNode[];
		edges: Edge[];
	}
	
	let { nodes, edges }: Props = $props();
	
	// Canvas state
	let zoom = $state(1);
	let panX = $state(0);
	let panY = $state(0);
	let selectedNode = $state<PlanNode | null>(null);
	let isDragging = $state(false);
	let dragStart = $state({ x: 0, y: 0 });
	let canvasElement: SVGSVGElement;
	let containerElement: HTMLDivElement;
	let containerWidth = $state(800);
	let containerHeight = $state(600);
	
	// Node colors by type
	const nodeColors = {
		goal: 'hsl(var(--chart-1))',
		step: 'hsl(var(--chart-2))',
		action: 'hsl(var(--chart-3))',
		tool: 'hsl(var(--chart-4))'
	};
	
	// Status colors
	const statusColors = {
		pending: 'opacity-40',
		active: 'opacity-100 animate-pulse-glow',
		completed: 'opacity-80',
		error: 'opacity-100'
	};
	
	function handleZoomIn() {
		zoom = Math.min(zoom + 0.2, 3);
	}
	
	function handleZoomOut() {
		zoom = Math.max(zoom - 0.2, 0.5);
	}
	
	function fitToView() {
		// Calculate bounds
		const minX = Math.min(...nodes.map(n => n.x));
		const maxX = Math.max(...nodes.map(n => n.x));
		const minY = Math.min(...nodes.map(n => n.y));
		const maxY = Math.max(...nodes.map(n => n.y));
		
		const width = maxX - minX + 200;
		const height = maxY - minY + 200;
		
		// Center the content
		panX = -minX + 100;
		panY = -minY + 100;
		
		// Zoom to fit using actual container dimensions
		zoom = Math.min(containerWidth / width, containerHeight / height, 1);
	}
	
	function updateContainerSize() {
		if (containerElement) {
			containerWidth = containerElement.clientWidth;
			containerHeight = containerElement.clientHeight;
		}
	}
	
	onMount(() => {
		updateContainerSize();
		
		// Update on window resize
		const resizeObserver = new ResizeObserver(() => {
			updateContainerSize();
		});
		
		if (containerElement) {
			resizeObserver.observe(containerElement);
		}
		
		return () => {
			resizeObserver.disconnect();
		};
	});
	
	function handleMouseDown(e: MouseEvent) {
		isDragging = true;
		dragStart = { x: e.clientX - panX, y: e.clientY - panY };
	}
	
	function handleMouseMove(e: MouseEvent) {
		if (!isDragging) return;
		panX = e.clientX - dragStart.x;
		panY = e.clientY - dragStart.y;
	}
	
	function handleMouseUp() {
		isDragging = false;
	}
	
	function getNodePosition(nodeId: string) {
		const node = nodes.find(n => n.id === nodeId);
		return node ? { x: node.x, y: node.y } : { x: 0, y: 0 };
	}
	
	function splitTextToLines(text: string, maxCharsPerLine: number, maxLines: number): string[] {
		const words = text.split(' ');
		const lines: string[] = [];
		let currentLine = '';
		
		for (const word of words) {
			const testLine = currentLine ? `${currentLine} ${word}` : word;
			if (testLine.length <= maxCharsPerLine) {
				currentLine = testLine;
			} else {
				if (currentLine) lines.push(currentLine);
				currentLine = word;
			}
		}
		if (currentLine) lines.push(currentLine);
		
		// Limit to maxLines
		if (lines.length > maxLines) {
			lines[maxLines - 1] = lines[maxLines - 1].slice(0, maxCharsPerLine - 3) + '...';
			return lines.slice(0, maxLines);
		}
		return lines;
	}
	
	function isActiveEdge(edge: Edge) {
		const fromNode = nodes.find(n => n.id === edge.from);
		const toNode = nodes.find(n => n.id === edge.to);
		return fromNode?.status === 'active' || toNode?.status === 'active';
	}
	
	function handleNodeClick(node: PlanNode) {
		selectedNode = node;
	}
</script>

<div
	bind:this={containerElement}
	class="plan-canvas-container relative h-[600px] w-full overflow-hidden bg-secondary/20 rounded-lg border border-border"
>
	<!-- Canvas Controls -->
	<div class="absolute top-4 right-4 z-10 flex gap-2">
		<Button size="sm" variant="outline" onclick={handleZoomIn}>
			<ZoomIn class="size-4" />
		</Button>
		<Button size="sm" variant="outline" onclick={handleZoomOut}>
			<ZoomOut class="size-4" />
		</Button>
		<Button size="sm" variant="outline" onclick={fitToView}>
			<Maximize2 class="size-4" />
		</Button>
	</div>
	
	<!-- Legend -->
	<div class="absolute top-4 left-4 z-10 bg-card/95 border border-border rounded-lg p-3 space-y-2 shadow-lg">
		<div class="text-xs font-semibold mb-2">Node Types</div>
		<div class="flex items-center gap-2 text-xs">
			<svg width="32" height="32" viewBox="-16 -16 32 32" class="flex-shrink-0">
				<circle r="12" fill={nodeColors.goal} class="stroke-background" stroke-width="2" />
			</svg>
			<span>Goal</span>
		</div>
		<div class="flex items-center gap-2 text-xs">
			<svg width="24" height="24" viewBox="-12 -12 24 24" class="flex-shrink-0">
				<rect x="-10" y="-8" width="20" height="16" rx="2" fill={nodeColors.step} class="stroke-background" stroke-width="1.5" />
			</svg>
			<span>Step</span>
		</div>
		<div class="flex items-center gap-2 text-xs">
			<svg width="20" height="20" viewBox="-10 -10 20 20" class="flex-shrink-0">
				<rect x="-8" y="-6" width="16" height="12" rx="1.5" fill={nodeColors.action} class="stroke-background" stroke-width="1.5" />
			</svg>
			<span>Action</span>
		</div>
		<div class="flex items-center gap-2 text-xs">
			<svg width="20" height="20" viewBox="-10 -10 20 20" class="flex-shrink-0">
				<path d="M0,-7 L8,0 L0,7 L-8,0 Z" fill={nodeColors.tool} class="stroke-background" stroke-width="1.5" />
			</svg>
			<span>Tool</span>
		</div>
	</div>
	
	<!-- SVG Canvas -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="plan-canvas w-full h-full cursor-grab active:cursor-grabbing"
		class:cursor-grabbing={isDragging}
		onmousedown={handleMouseDown}
		onmousemove={handleMouseMove}
		onmouseup={handleMouseUp}
		onmouseleave={handleMouseUp}
	>
		<svg
			bind:this={canvasElement}
			class="w-full h-full"
			style="transform: translate({panX}px, {panY}px) scale({zoom})"
		>
			<defs>
				<!-- Animated gradient for active edges -->
				<linearGradient id="activeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
					<stop offset="0%" style="stop-color:hsl(var(--primary));stop-opacity:0" />
					<stop offset="50%" style="stop-color:hsl(var(--primary));stop-opacity:1" />
					<stop offset="100%" style="stop-color:hsl(var(--primary));stop-opacity:0" />
					<animate attributeName="x1" values="0%;100%" dur="2s" repeatCount="indefinite" />
					<animate attributeName="x2" values="100%;200%" dur="2s" repeatCount="indefinite" />
				</linearGradient>
				
				<!-- Arrow marker -->
				<marker
					id="arrowhead"
					markerWidth="10"
					markerHeight="10"
					refX="9"
					refY="3"
					orient="auto"
				>
					<polygon points="0 0, 10 3, 0 6" fill="hsl(var(--border))" />
				</marker>
				
				<marker
					id="arrowhead-active"
					markerWidth="10"
					markerHeight="10"
					refX="9"
					refY="3"
					orient="auto"
				>
					<polygon points="0 0, 10 3, 0 6" fill="hsl(var(--primary))" />
				</marker>
			</defs>
			
			<!-- Edges -->
			<g class="edges">
				{#each edges as edge}
					{@const fromPos = getNodePosition(edge.from)}
					{@const toPos = getNodePosition(edge.to)}
					{@const isActive = isActiveEdge(edge)}
					<line
						x1={fromPos.x}
						y1={fromPos.y}
						x2={toPos.x}
						y2={toPos.y}
						class="transition-all duration-300"
						class:stroke-border={!isActive}
						class:stroke-primary={isActive}
						stroke-width={isActive ? 3 : 2}
						marker-end={isActive ? 'url(#arrowhead-active)' : 'url(#arrowhead)'}
					/>
					{#if isActive}
						<line
							x1={fromPos.x}
							y1={fromPos.y}
							x2={toPos.x}
							y2={toPos.y}
							stroke="url(#activeGradient)"
							stroke-width="3"
							stroke-dasharray="5 5"
							class="animate-data-flow"
						/>
					{/if}
				{/each}
			</g>
			
			<!-- Nodes -->
			<g class="nodes">
				{#each nodes as node}
					<!-- svelte-ignore a11y_click_events_have_key_events -->
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<g
						transform="translate({node.x}, {node.y})"
						class="cursor-pointer transition-transform hover:scale-105 {statusColors[node.status]}"
						onclick={() => handleNodeClick(node)}
					>
						{#if node.type === 'goal'}
							<!-- Goal node: Large circle -->
							<circle r="45" fill={nodeColors.goal} class="stroke-background" stroke-width="3" />
							<text
								text-anchor="middle"
								dy="0.3em"
								class="fill-white dark:fill-white font-bold text-base select-none"
							>
								{node.label.charAt(0)}
							</text>
							{@const lines = splitTextToLines(node.label, 17, 2)}
							{@const lineHeight = 11}
							{@const totalHeight = lines.length * lineHeight}
							{@const startY = 60 + (lineHeight / 2) - (totalHeight / 2)}
							{#each lines as line, i}
								<text
									text-anchor="middle"
									dominant-baseline="middle"
									y={startY + i * lineHeight}
									class="fill-foreground dark:fill-white text-[10px] font-medium select-none"
								>
									{line}
								</text>
							{/each}
						{:else if node.type === 'step'}
							<!-- Step node: Rounded rectangle -->
							<rect
								x="-55"
								y="-32"
								width="110"
								height="64"
								rx="6"
								fill={nodeColors.step}
								class="stroke-background"
								stroke-width="2"
							/>
							{@const lines = splitTextToLines(node.label, 15, 3)}
							{@const lineHeight = 11}
							{@const totalHeight = lines.length * lineHeight}
							{@const startY = (lineHeight / 2) - (totalHeight / 2)}
							{#each lines as line, i}
								<text
									text-anchor="middle"
									dominant-baseline="middle"
									y={startY + i * lineHeight}
									class="fill-white dark:fill-white text-[10px] font-semibold select-none"
								>
									{line}
								</text>
							{/each}
							{#if node.status === 'completed'}
								<circle cx="35" cy="-15" r="8" fill="hsl(var(--primary))" />
								<text x="35" y="-15" text-anchor="middle" dy="0.3em" class="fill-white dark:fill-white text-xs font-bold">✓</text>
							{/if}
						{:else if node.type === 'action'}
							<!-- Action node: Small rounded rectangle -->
							<rect
								x="-45"
								y="-26"
								width="90"
								height="52"
								rx="4"
								fill={nodeColors.action}
								class="stroke-background"
								stroke-width="2"
							/>
							{@const lines = splitTextToLines(node.label, 13, 3)}
							{@const lineHeight = 10}
							{@const totalHeight = lines.length * lineHeight}
							{@const startY = (lineHeight / 2) - (totalHeight / 2)}
							{#each lines as line, i}
								<text
									text-anchor="middle"
									dominant-baseline="middle"
									y={startY + i * lineHeight}
									class="fill-white dark:fill-white text-[9px] font-medium select-none"
								>
									{line}
								</text>
							{/each}
						{:else if node.type === 'tool'}
							<!-- Tool node: Diamond shape -->
							<path
					d="M0,-28 L35,0 L0,28 L-35,0 Z"
								fill={nodeColors.tool}
								class="stroke-background"
								stroke-width="2"
							/>
							{@const lines = splitTextToLines(node.label, 12, 2)}
							{@const lineHeight = 9}
							{@const totalHeight = lines.length * lineHeight}
							{@const startY = (lineHeight / 2) - (totalHeight / 2)}
							{#each lines as line, i}
								<text
									text-anchor="middle"
									dominant-baseline="middle"
									y={startY + i * lineHeight}
									class="fill-white dark:fill-white text-[8px] font-mono select-none"
								>
									{line}
								</text>
							{/each}
						{/if}
					</g>
				{/each}
			</g>
		</svg>
	</div>
	
	<!-- Context Panel (selected node) -->
	{#if selectedNode}
		<Card.Root class="absolute bottom-4 left-4 w-96 shadow-2xl animate-slide-in-up">
			<Card.Header class="pb-3">
				<div class="flex items-start justify-between">
					<div class="flex-1">
						<Card.Title class="text-base">{selectedNode.label}</Card.Title>
						<div class="flex items-center gap-2 mt-2">
							<Badge variant="outline" class="text-xs">{selectedNode.type}</Badge>
							<Badge
								variant={selectedNode.status === 'completed' ? 'default' : selectedNode.status === 'active' ? 'secondary' : 'outline'}
								class="text-xs"
							>
								{selectedNode.status}
							</Badge>
						</div>
					</div>
					<Button
						size="icon"
						variant="ghost"
						onclick={() => selectedNode = null}
					>
						<span class="text-lg">×</span>
					</Button>
				</div>
			</Card.Header>
			<Card.Content class="space-y-3 text-sm">
				<!-- Task Description -->
				<div class="space-y-1">
					<span class="text-xs text-muted-foreground">Description</span>
					<p class="text-sm">{selectedNode.label}</p>
				</div>
				
				{#if selectedNode.children.length > 0}
					<div class="space-y-1">
						<span class="text-xs text-muted-foreground">Dependencies</span>
						<div class="flex flex-wrap gap-1">
							{#each selectedNode.children as childId}
								{@const child = nodes.find(n => n.id === childId)}
								{#if child}
									<Badge variant="outline" class="text-[10px]">
										{child.label.slice(0, 12)}
									</Badge>
								{/if}
							{/each}
						</div>
					</div>
				{/if}
				
				{#if selectedNode.metadata}
					<div class="space-y-1">
						<span class="text-xs text-muted-foreground">Metadata</span>
						<pre class="text-[10px] bg-muted/50 p-2 rounded overflow-x-auto">{JSON.stringify(selectedNode.metadata, null, 2)}</pre>
					</div>
				{/if}
				
				<div class="pt-2 border-t border-border">
					<div class="flex items-center gap-1 text-xs text-muted-foreground">
						<Info class="size-3" />
						<span>Click nodes to explore the plan structure</span>
					</div>
				</div>
			</Card.Content>
		</Card.Root>
	{/if}
</div>

<style>
	@keyframes data-flow {
		0% {
			stroke-dashoffset: 10;
		}
		100% {
			stroke-dashoffset: 0;
		}
	}
	
	.animate-data-flow {
		animation: data-flow 1s linear infinite;
	}
</style>