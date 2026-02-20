<script lang="ts">
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Resizable from '$lib/components/ui/resizable';
	import { Separator } from '$lib/components/ui/separator';
	import { ScrollArea } from '$lib/components/ui/scroll-area';
	import { PanelRight, History, Sparkles, LandPlot } from 'lucide-svelte';

	import MessageList from '$lib/components/chat/MessageList.svelte';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import EnhancedPlanTimeline from '$lib/components/planning/EnhancedPlanTimeline.svelte';

	// State
	let messages = $state<any[]>([
		{
			role: 'assistant',
			content: 'Hello! I am Dolphin, your AI coding assistant. How can I help you today?',
			timestamp: new Date().toLocaleTimeString()
		}
	]);
	let isProcessing = $state(false);
	let showPlanPanel = $state(false);

	// Mock Plan Data
	const mockPlanPhases = [
		{
			id: 'phase-1',
			name: 'Analysis',
			status: 'completed' as const,
			steps: [
				{
					id: '1-1',
					description: 'Analyze user request',
					status: 'completed' as const,
					actualTime: 1500,
					estimatedTime: 2000
				},
				{
					id: '1-2',
					description: 'Identify relevant files',
					status: 'completed' as const,
					actualTime: 800,
					estimatedTime: 1000
				}
			]
		},
		{
			id: 'phase-2',
			name: 'Implementation',
			status: 'active' as const,
			steps: [
				{
					id: '2-1',
					description: 'Scaffold components',
					status: 'running' as const,
					context: 'Working on src/routes/+page.svelte'
				},
				{
					id: '2-2',
					description: 'Integrate state management',
					status: 'pending' as const
				}
			]
		}
	];

	function handleSend(content: string) {
		// Add user message
		messages = [
			...messages,
			{
				role: 'user',
				content,
				timestamp: new Date().toLocaleTimeString()
			}
		];

		isProcessing = true;

		// Mock AI response
		setTimeout(() => {
			messages = [
				...messages,
				{
					role: 'assistant',
					content: "I'm processing your request. This is a mock response to demonstrate the UI.",
					timestamp: new Date().toLocaleTimeString()
				}
			];
			isProcessing = false;
		}, 1500);
	}

	function togglePlanPanel() {
		showPlanPanel = !showPlanPanel;
	}
</script>

<div class="relative flex h-full w-full overflow-hidden bg-background">
	<!-- Main Chat Area -->
	<div class="flex flex-1 flex-col min-w-0">
		<!-- Header -->
		<header class="flex items-center justify-between px-4 py-2 border-b h-12 shrink-0">
			<div class="flex items-center gap-2 font-semibold">
				<Sparkles class="size-4 text-primary" />
				<span>Dolphin</span>
			</div>
			<div class="flex items-center gap-2">
				<Button variant="ghost" size="icon" onclick={togglePlanPanel} title="Toggle Plan Panel">
					<LandPlot class="size-4" />
				</Button>
			</div>
		</header>

		<!-- Messages -->
		<div class="flex-1 overflow-hidden">
			<MessageList {messages} />
		</div>

		<!-- Input Area -->
		<div class="p-4 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
			<div class="max-w-3xl mx-auto">
				<ChatInput
					onSend={handleSend}
					{isProcessing}
					hasActiveConversation={messages.length > 1}
				/>
			</div>
		</div>
	</div>

	<!-- Right Panel (Plan) -->
	{#if showPlanPanel}
		<!-- Overlay Backdrop (optional, for clicking outside to close) -->
		<div
			class="absolute inset-0 bg-background/50 backdrop-blur-sm z-40"
			onclick={togglePlanPanel}
			onkeydown={(e) => e.key === 'Escape' && togglePlanPanel()}
			role="button"
			tabindex="0"
			aria-label="Close plan panel"
		></div>

		<!-- Panel -->
		<div
			class="absolute right-0 top-0 bottom-0 w-[90%] border-l flex flex-col bg-background shadow-2xl z-50 transition-transform duration-300 ease-in-out"
			role="dialog"
			aria-label="Current Plan"
		>
			<div class="flex items-center justify-between px-4 py-2 border-b h-12 font-medium bg-muted/20">
				<div class="flex items-center">
					<History class="size-4 mr-2 text-muted-foreground" />
					<span>Current Plan</span>
				</div>
				<Button variant="ghost" size="icon" class="h-8 w-8" onclick={togglePlanPanel}>
					<PanelRight class="size-4" />
					<span class="sr-only">Close</span>
				</Button>
			</div>
			<ScrollArea class="flex-1">
				<div class="p-4">
					<EnhancedPlanTimeline phases={mockPlanPhases} />
				</div>
			</ScrollArea>
		</div>
	{/if}
</div>
