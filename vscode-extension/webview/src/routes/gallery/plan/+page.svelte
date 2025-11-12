<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { Badge } from '$lib/components/ui/badge';
	import * as Tabs from '$lib/components/ui/tabs';
	import { Palette, Network, Target, Clock } from 'lucide-svelte';
	import GalleryShowcase from '$lib/components/GalleryShowcase.svelte';
	import PlanCanvas from '$lib/components/planning/PlanCanvas.svelte';
	import EnhancedPlanTimeline from '$lib/components/planning/EnhancedPlanTimeline.svelte';
	import GoalContext from '$lib/components/planning/GoalContext.svelte';
	
	// Mock data for PlanCanvas
	const mockNodes = [
		{
			id: 'goal-1',
			type: 'goal' as const,
			label: 'Build Authentication System',
			status: 'active' as const,
			x: 400,
			y: 100,
			progress: 0.65,
			children: ['step-1', 'step-2', 'step-3']
		},
		{
			id: 'step-1',
			type: 'step' as const,
			label: 'Design Database Schema',
			status: 'completed' as const,
			x: 200,
			y: 250,
			children: ['action-1', 'action-2']
		},
		{
			id: 'step-2',
			type: 'step' as const,
			label: 'Implement JWT Auth',
			status: 'active' as const,
			x: 400,
			y: 250,
			children: ['action-3', 'action-4']
		},
		{
			id: 'step-3',
			type: 'step' as const,
			label: 'Add OAuth Support',
			status: 'pending' as const,
			x: 600,
			y: 250,
			children: ['action-5']
		},
		{
			id: 'action-1',
			type: 'action' as const,
			label: 'Create users table',
			status: 'completed' as const,
			x: 150,
			y: 400,
			children: []
		},
		{
			id: 'action-2',
			type: 'action' as const,
			label: 'Add indexes',
			status: 'completed' as const,
			x: 250,
			y: 400,
			children: []
		},
		{
			id: 'action-3',
			type: 'action' as const,
			label: 'Generate tokens',
			status: 'completed' as const,
			x: 350,
			y: 400,
			children: ['tool-1']
		},
		{
			id: 'action-4',
			type: 'action' as const,
			label: 'Verify middleware',
			status: 'active' as const,
			x: 450,
			y: 400,
			children: ['tool-2']
		},
		{
			id: 'action-5',
			type: 'action' as const,
			label: 'OAuth providers',
			status: 'pending' as const,
			x: 600,
			y: 400,
			children: []
		},
		{
			id: 'tool-1',
			type: 'tool' as const,
			label: 'write_to_file',
			status: 'completed' as const,
			x: 350,
			y: 520,
			children: [],
			metadata: { path: 'src/auth/jwt.ts' }
		},
		{
			id: 'tool-2',
			type: 'tool' as const,
			label: 'execute_command',
			status: 'active' as const,
			x: 450,
			y: 520,
			children: [],
			metadata: { command: 'npm test auth.test.ts' }
		}
	];
	
	const mockEdges = [
		{ from: 'goal-1', to: 'step-1' },
		{ from: 'goal-1', to: 'step-2' },
		{ from: 'goal-1', to: 'step-3' },
		{ from: 'step-1', to: 'action-1' },
		{ from: 'step-1', to: 'action-2' },
		{ from: 'step-2', to: 'action-3' },
		{ from: 'step-2', to: 'action-4' },
		{ from: 'step-3', to: 'action-5' },
		{ from: 'action-3', to: 'tool-1' },
		{ from: 'action-4', to: 'tool-2' }
	];
	
	// Mock data for EnhancedPlanTimeline
	const mockPlanPhases = [
		{
			id: 'phase-1',
			name: 'Planning',
			status: 'completed' as const,
			steps: [
				{
					id: '1-1',
					description: 'Analyze requirements',
					status: 'completed' as const,
					estimatedTime: 300000,
					actualTime: 280000,
					context: 'Reviewed authentication specifications'
				},
				{
					id: '1-2',
					description: 'Design architecture',
					status: 'completed' as const,
					estimatedTime: 600000,
					actualTime: 720000,
					context: 'Created database schema and API design'
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
					description: 'Setup database',
					status: 'completed' as const,
					estimatedTime: 400000,
					actualTime: 350000
				},
				{
					id: '2-2',
					description: 'Implement JWT auth',
					status: 'running' as const,
					estimatedTime: 800000,
					actualTime: 600000
				},
				{
					id: '2-3',
					description: 'Add middleware',
					status: 'pending' as const,
					estimatedTime: 500000
				}
			]
		},
		{
			id: 'phase-3',
			name: 'Testing',
			status: 'pending' as const,
			steps: [
				{
					id: '3-1',
					description: 'Write unit tests',
					status: 'pending' as const,
					estimatedTime: 600000
				},
				{
					id: '3-2',
					description: 'Integration testing',
					status: 'pending' as const,
					estimatedTime: 400000
				}
			]
		}
	];
	
	// Mock data for GoalContext
	const mockGoalContext = {
		currentGoal: 'Build Authentication System',
		reasoningChain: [
			{
				step: 'Identify authentication requirements',
				reasoning: 'System needs secure user authentication with JWT tokens and optional OAuth',
				confidence: 0.95
			},
			{
				step: 'Choose JWT over sessions',
				reasoning: 'JWT provides stateless authentication, better scalability for distributed systems',
				confidence: 0.85
			},
			{
				step: 'Design token refresh strategy',
				reasoning: 'Implement refresh tokens to maintain security while providing good UX',
				confidence: 0.8
			},
			{
				step: 'Plan OAuth integration',
				reasoning: 'Add OAuth as optional enhancement for social login providers',
				confidence: 0.75
			}
		],
		alternatives: [
			{
				approach: 'Session-based authentication',
				pros: ['Simpler implementation', 'Server-side control', 'Easy to revoke'],
				cons: ['Not stateless', 'Scaling challenges', 'Requires session store'],
				whyNotChosen: 'Does not fit distributed architecture requirements'
			},
			{
				approach: 'OAuth-only authentication',
				pros: ['No password management', 'Trusted providers', 'Social login UX'],
				cons: ['External dependency', 'Limited to OAuth providers', 'Privacy concerns'],
				whyNotChosen: 'Need to support email/password authentication as primary method'
			}
		],
		successCriteria: [
			'Secure password hashing with bcrypt',
			'JWT tokens with 15-minute expiration',
			'Refresh token rotation implemented',
			'Rate limiting on auth endpoints',
			'HTTPS-only cookie transmission',
			'OAuth providers (Google, GitHub) integrated'
		]
	};
	
	let showGoalContext = $state(false);
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-7xl mx-auto">
		<div class="mb-8">
			<h1 class="text-4xl font-bold mb-2">Phase 2: Planning Visualization System</h1>
			<p class="text-muted-foreground mb-4">
				Interactive planning visualizations that make the agent's thinking process visible and beautiful
			</p>
			<div class="flex items-center gap-2 text-sm">
				<Badge variant="outline" class="gap-1">
					<Palette class="size-3" />
					Phase 2: Weeks 2-4
				</Badge>
				<Badge variant="default">Ready for Sign-off</Badge>
			</div>
		</div>

		<!-- Tabbed Navigation -->
		<Tabs.Root value="canvas" class="mb-8">
			<Tabs.List class="grid w-full grid-cols-3">
				<Tabs.Trigger value="canvas">
					<Network class="size-4 mr-2" />
					Plan Canvas
				</Tabs.Trigger>
				<Tabs.Trigger value="timeline">
					<Clock class="size-4 mr-2" />
					Enhanced Timeline
				</Tabs.Trigger>
				<Tabs.Trigger value="context">
					<Target class="size-4 mr-2" />
					Goal Context
				</Tabs.Trigger>
			</Tabs.List>

			<!-- Plan Canvas Tab -->
			<Tabs.Content value="canvas" class="space-y-6 mt-6">
				<Card class="bg-primary/5 border-primary/20">
					<CardContent class="p-6">
						<div class="space-y-4">
							<div>
								<h3 class="text-xl font-bold mb-2">2.1 Interactive Plan Canvas ⭐ MUST-HAVE</h3>
								<p class="text-sm text-muted-foreground mb-4">
									Node-based graph visualization showing the hierarchical structure of agent planning. Features pan, zoom, and interactive node exploration.
								</p>
								<div class="flex gap-2 flex-wrap">
									<Badge variant="outline">Pan & Zoom</Badge>
									<Badge variant="outline">Interactive Nodes</Badge>
									<Badge variant="outline">Real-time Updates</Badge>
									<Badge variant="outline">Progress Rings</Badge>
								</div>
							</div>
						</div>
					</CardContent>
				</Card>

				<GalleryShowcase
					title="Plan Canvas - Node-Based Visualization"
					description="Interactive graph showing goal → step → action → tool hierarchy with zoom, pan, and node selection"
				>
					{#snippet children()}
						<PlanCanvas nodes={mockNodes} edges={mockEdges} />
					{/snippet}
				</GalleryShowcase>

				<Card>
					<CardHeader>
						<CardTitle>Features & Interactions</CardTitle>
						<CardDescription>What makes this visualization powerful</CardDescription>
					</CardHeader>
					<CardContent>
						<div class="grid md:grid-cols-2 gap-6 text-sm">
							<div class="space-y-2">
								<h4 class="font-semibold">Node Types</h4>
								<ul class="list-disc list-inside space-y-1 text-muted-foreground">
									<li><strong>Goal:</strong> Top-level objective with progress ring</li>
									<li><strong>Step:</strong> Sub-tasks with status indicators</li>
									<li><strong>Action:</strong> Specific operations</li>
									<li><strong>Tool:</strong> Tool calls with metadata preview</li>
								</ul>
							</div>
							
							<div class="space-y-2">
								<h4 class="font-semibold">Interactions</h4>
								<ul class="list-disc list-inside space-y-1 text-muted-foreground">
									<li>Click nodes to view details in context panel</li>
									<li>Drag canvas to pan around large plans</li>
									<li>Mouse wheel or buttons to zoom in/out</li>
									<li>Animated edges show data flow</li>
								</ul>
							</div>
						</div>
					</CardContent>
				</Card>
			</Tabs.Content>

			<!-- Enhanced Timeline Tab -->
			<Tabs.Content value="timeline" class="space-y-6 mt-6">
				<Card class="bg-primary/5 border-primary/20">
					<CardContent class="p-6">
						<div class="space-y-4">
							<div>
								<h3 class="text-xl font-bold mb-2">2.2 Enhanced Plan Timeline</h3>
								<p class="text-sm text-muted-foreground mb-4">
									Evolution of the existing PlanTimeline with accordion grouping, tooltips, time comparisons, and plan branch visualization.
								</p>
								<div class="flex gap-2 flex-wrap">
									<Badge variant="outline">Collapsible Phases</Badge>
									<Badge variant="outline">Time Estimates</Badge>
									<Badge variant="outline">Rich Tooltips</Badge>
									<Badge variant="outline">Branch Visualization</Badge>
								</div>
							</div>
						</div>
					</CardContent>
				</Card>

				<GalleryShowcase
					title="Enhanced Timeline - Grouped by Phases"
					description="Accordion-based timeline with collapsible sections, time comparisons, and contextual tooltips"
				>
					{#snippet children()}
						<EnhancedPlanTimeline phases={mockPlanPhases} />
					{/snippet}
				</GalleryShowcase>

				<Card>
					<CardHeader>
						<CardTitle>Enhancements Over Basic Timeline</CardTitle>
						<CardDescription>New features compared to Phase 1</CardDescription>
					</CardHeader>
					<CardContent>
						<div class="grid md:grid-cols-2 gap-6 text-sm">
							<div class="space-y-2">
								<h4 class="font-semibold">New Features</h4>
								<ul class="list-disc list-inside space-y-1 text-muted-foreground">
									<li>Accordion grouping by phase/category</li>
									<li>Estimated vs actual time comparison</li>
									<li>Rich tooltips with context</li>
									<li>Plan branch visualization for revisions</li>
								</ul>
							</div>
							
							<div class="space-y-2">
								<h4 class="font-semibold">Visual Enhancements</h4>
								<ul class="list-disc list-inside space-y-1 text-muted-foreground">
									<li>Progress counters per phase</li>
									<li>Color-coded time variance indicators</li>
									<li>Smooth collapse/expand animations</li>
									<li>Compact view for completed phases</li>
								</ul>
							</div>
						</div>
					</CardContent>
				</Card>
			</Tabs.Content>

			<!-- Goal Context Tab -->
			<Tabs.Content value="context" class="space-y-6 mt-6">
				<Card class="bg-primary/5 border-primary/20">
					<CardContent class="p-6">
						<div class="space-y-4">
							<div>
								<h3 class="text-xl font-bold mb-2">2.3 Goal-Oriented Context Panel</h3>
								<p class="text-sm text-muted-foreground mb-4">
									Slide-out panel showing the agent's reasoning chain, alternative approaches considered, and success criteria for the current goal.
								</p>
								<div class="flex gap-2 flex-wrap">
									<Badge variant="outline">Reasoning Chain</Badge>
									<Badge variant="outline">Alternatives</Badge>
									<Badge variant="outline">Confidence Levels</Badge>
									<Badge variant="outline">Success Criteria</Badge>
								</div>
							</div>
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardHeader>
						<CardTitle>Goal Context Panel Preview</CardTitle>
						<CardDescription>Click to open the context panel with detailed reasoning</CardDescription>
					</CardHeader>
					<CardContent>
						<Button onclick={() => showGoalContext = true} size="lg">
							<Target class="size-4 mr-2" />
							Open Goal Context Panel
						</Button>
						
						<div class="mt-6 text-sm text-muted-foreground space-y-2">
							<p class="font-semibold text-foreground">Panel Contents:</p>
							<ul class="list-disc list-inside space-y-1 text-xs">
								<li>Current goal description and status</li>
								<li>Step-by-step reasoning chain with confidence levels</li>
								<li>Alternative approaches with pros/cons analysis</li>
								<li>Why alternatives were not chosen (transparency)</li>
								<li>Success criteria checklist</li>
							</ul>
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardHeader>
						<CardTitle>Innovation Highlight</CardTitle>
						<CardDescription>Why this changes everything</CardDescription>
					</CardHeader>
					<CardContent>
						<div class="space-y-4 text-sm">
							<p class="text-muted-foreground">
								Unlike traditional chat interfaces that hide the agent's decision-making process, the Goal Context Panel provides <strong>complete transparency</strong> into how the agent thinks.
							</p>
							<div class="grid md:grid-cols-2 gap-4">
								<div class="p-4 bg-muted/50 rounded-lg space-y-2">
									<h4 class="font-semibold text-emerald-600 dark:text-emerald-400">Benefits</h4>
									<ul class="list-disc list-inside space-y-1 text-xs text-muted-foreground">
										<li>Builds user trust through transparency</li>
										<li>Educational - users learn AI reasoning patterns</li>
										<li>Enables informed decision-making</li>
										<li>Shows alternatives for learning</li>
									</ul>
								</div>
								<div class="p-4 bg-muted/50 rounded-lg space-y-2">
									<h4 class="font-semibold text-primary">Use Cases</h4>
									<ul class="list-disc list-inside space-y-1 text-xs text-muted-foreground">
										<li>Debugging agent decisions</li>
										<li>Understanding trade-offs</li>
										<li>Learning best practices</li>
										<li>Auditing agent behavior</li>
									</ul>
								</div>
							</div>
						</div>
					</CardContent>
				</Card>
			</Tabs.Content>
		</Tabs.Root>

		<Separator class="my-8" />

		<!-- Implementation Notes -->
		<section class="space-y-6">
			<div>
				<h2 class="text-2xl font-bold mb-2">Implementation Notes</h2>
				<p class="text-sm text-muted-foreground">
					Key technical considerations for Phase 2 development
				</p>
			</div>

			<div class="grid md:grid-cols-2 gap-6">
				<Card>
					<CardHeader>
						<CardTitle>Required shadcn-svelte Components</CardTitle>
					</CardHeader>
					<CardContent>
						<pre class="text-xs bg-muted/50 p-4 rounded overflow-x-auto"><code>npx shadcn-svelte@latest add \
  popover command dialog sheet \
  accordion collapsible tooltip \
  progress checkbox</code></pre>
					</CardContent>
				</Card>

				<Card>
					<CardHeader>
						<CardTitle>Performance Targets</CardTitle>
					</CardHeader>
					<CardContent class="text-sm space-y-2">
						<div class="flex justify-between">
							<span class="text-muted-foreground">Canvas interactions:</span>
							<Badge variant="outline">60 FPS</Badge>
						</div>
						<div class="flex justify-between">
							<span class="text-muted-foreground">Node rendering:</span>
							<Badge variant="outline">&lt; 50ms</Badge>
						</div>
						<div class="flex justify-between">
							<span class="text-muted-foreground">Panel animations:</span>
							<Badge variant="outline">&lt; 200ms</Badge>
						</div>
					</CardContent>
				</Card>
			</div>
		</section>
	</div>
</div>

{#if showGoalContext}
	<GoalContext
		{...mockGoalContext}
		open={showGoalContext}
		onClose={() => showGoalContext = false}
	/>
{/if}