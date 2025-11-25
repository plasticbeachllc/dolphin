<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import * as Tabs from '$lib/components/ui/tabs';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import { ChevronDown, ChevronRight, FileCode, Info, MessageSquare, ArrowRight, Palette, Loader, Code, Target, Clock, User, Settings as SettingsIcon, Database, Zap, Bell, Mail, Calendar, Book } from 'lucide-svelte';
	import MessageCard from '$lib/components/chat/MessageCard.svelte';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import ToolCallCard from '$lib/components/tools/ToolCallCard.svelte';
	import DiffViewer from '$lib/components/tools/DiffViewer.svelte';
	import PlanTimeline from '$lib/components/PlanTimeline.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import ErrorAlert from '$lib/components/ErrorAlert.svelte';
	import AuthStatus from '$lib/components/AuthStatus.svelte';
	import GalleryShowcase from '$lib/components/GalleryShowcase.svelte';
	import AnimationGallery from '$lib/components/AnimationGallery.svelte';
	import LoadingStates from '$lib/components/LoadingStates.svelte';
	import EnhancedPlanTimeline from '$lib/components/planning/EnhancedPlanTimeline.svelte';
	import GoalContext from '$lib/components/planning/GoalContext.svelte';
	import KBManagementPanel from '$lib/components/kb/KBManagementPanel.svelte';
	
	// Sample data
	let showConfirmDialog = $state(false);
	let showInitDialog = $state(false);
	let showErrorAlert = $state(true);
	let diffExpanded = $state(true);
	

	// Mock parsed diff data - skip the parser to avoid formatting issues
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

	const planSteps = [
		{ id: '1', description: 'Analyze requirements', status: 'completed' as const },
		{ id: '2', description: 'Design architecture', status: 'completed' as const },
		{ id: '3', description: 'Implement features', status: 'running' as const },
		{ id: '4', description: 'Write tests', status: 'pending' as const },
		{ id: '5', description: 'Deploy to production', status: 'pending' as const }
	];
	
	const sampleError = {
		code: 'FILE_NOT_FOUND',
		message: 'Could not find the requested file in the workspace',
		details: 'Stack trace:\n  at readFile (/path/to/file.ts:42)\n  at processRequest (/path/to/handler.ts:15)',
		suggestions: [
			'Check if the file path is correct',
			'Verify file exists in the workspace',
			'Try using an absolute path'
		],
			recoverable: true
		};
	
	function handleSend(message: string) {
		console.log('Message sent:', message);
	}
	
	function handleConfirmSelect(choice: string) {
		console.log('Confirmation choice:', choice);
		showConfirmDialog = false;
	}
	
	function handleErrorRetry() {
		console.log('Retrying operation');
	}
	
	// Mock data for EnhancedPlanTimeline
	const mockPlanPhases = [
		{
			id: 'phase-1',
			name: 'Plan',
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
			name: 'Exec',
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
			name: 'Test',
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
			}
		],
		alternatives: [
			{
				approach: 'Session-based authentication',
				pros: ['Simpler implementation', 'Server-side control'],
				cons: ['Not stateless', 'Scaling challenges'],
				whyNotChosen: 'Does not fit distributed architecture requirements'
			}
		],
		successCriteria: [
			'Secure password hashing with bcrypt',
			'JWT tokens with 15-minute expiration',
			'Rate limiting on auth endpoints'
		]
	};
	
	let showGoalContext = $state(false);
	
	// Settings state
	let apiKey = $state('');
	let model = $state('claude-sonnet-4');
	let temperature = $state(0.7);
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-6xl mx-auto">
		<div class="mb-8">
			<h1 class="text-4xl font-bold mb-2">Dolphin Design System Gallery</h1>
			<p class="text-muted-foreground mb-4">
				Complete design system with components, animations, and patterns for building exceptional AI experiences
			</p>
			<div class="flex items-center gap-2 text-sm">
				<Badge variant="outline" class="gap-1">
					<Palette class="size-3" />
					Phase 1: Foundation
				</Badge>
				<Badge variant="secondary">Updated 2025-11-11</Badge>
			</div>
		</div>

		<!-- Tabbed Navigation -->
		<Tabs.Root value="components" class="mb-8">
			<Tabs.List class="grid w-full grid-cols-5">
				<Tabs.Trigger value="components">
					<Code class="size-4 mr-2" />
					Components
				</Tabs.Trigger>
				<Tabs.Trigger value="animations">
					<Loader class="size-4 mr-2" />
					Animations
				</Tabs.Trigger>
				<Tabs.Trigger value="loading">
					<Loader class="size-4 mr-2" />
					Loading States
				</Tabs.Trigger>
				<Tabs.Trigger value="planning">
					<Palette class="size-4 mr-2" />
					Planning
				</Tabs.Trigger>
				<Tabs.Trigger value="featured">
					<MessageSquare class="size-4 mr-2" />
					Featured
				</Tabs.Trigger>
			</Tabs.List>

			<!-- Components Tab -->
			<Tabs.Content value="components" class="space-y-12 mt-6">
				{@render componentsSection()}
			</Tabs.Content>

			<!-- Animations Tab -->
			<Tabs.Content value="animations" class="mt-6">
				<AnimationGallery />
			</Tabs.Content>

			<!-- Loading States Tab -->
			<Tabs.Content value="loading" class="mt-6">
				<LoadingStates />
			</Tabs.Content>

			<!-- Planning Tab -->
			<Tabs.Content value="planning" class="space-y-6 mt-6">
				<Card class="bg-primary/5 border-primary/20">
					<CardContent class="p-6">
						<div class="space-y-4">
							<div>
								<h3 class="text-xl font-bold mb-2">Phase 2: Planning Visualization System</h3>
								<p class="text-sm text-muted-foreground mb-4">
									Interactive planning visualizations including enhanced timeline with accordion and goal context panel showing agent reasoning
								</p>
								<div class="flex gap-2 flex-wrap">
									<Badge variant="outline">Enhanced Timeline</Badge>
									<Badge variant="outline">Goal Context</Badge>
									<Badge variant="outline">Reasoning Chain</Badge>
									<Badge variant="default">Phase 2</Badge>
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
						<CardTitle>Goal Context Panel</CardTitle>
						<CardDescription>Agent reasoning transparency and decision-making insights</CardDescription>
					</CardHeader>
					<CardContent>
						<Button onclick={() => showGoalContext = true} size="lg">
							<Target class="size-4 mr-2" />
							Open Goal Context Panel
						</Button>
						
						<div class="mt-6 text-sm text-muted-foreground space-y-2">
							<p class="font-semibold text-foreground">Features:</p>
							<ul class="list-disc list-inside space-y-1 text-xs">
								<li>Step-by-step reasoning chain with confidence levels</li>
								<li>Alternative approaches with pros/cons analysis</li>
								<li>Success criteria checklist</li>
								<li>Complete transparency into agent thinking</li>
							</ul>
						</div>
					</CardContent>
				</Card>
			</Tabs.Content>
	
			<!-- Featured Tab -->
			<Tabs.Content value="featured" class="mt-6">
				{@render featuredSection()}
			</Tabs.Content>
		</Tabs.Root>
		
		{#if showGoalContext}
			<GoalContext
				{...mockGoalContext}
				open={showGoalContext}
				onClose={() => showGoalContext = false}
			/>
		{/if}
	</div>
</div>

{#snippet featuredSection()}
	<div class="space-y-8">
		<!-- Featured Section: Chat View Gallery -->
		<Card class="bg-primary/5 border-primary/20">
			<CardContent class="p-6">
				<div class="flex items-center justify-between">
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<Code class="h-6 w-6 text-primary" />
							<h3 class="text-xl font-bold">Chat View Gallery</h3>
							<Badge variant="default">New</Badge>
						</div>
						<p class="text-sm text-muted-foreground">
							Comprehensive reference for all chat formatting scenarios. View code blocks, tool calls, markdown rendering, inline code, tables, and edge cases.
						</p>
					</div>
					<Button size="lg" onclick={() => window.location.href = '/gallery/chat'}>
						View Gallery
						<ArrowRight class="h-4 w-4 ml-2" />
					</Button>
				</div>
			</CardContent>
		</Card>
		
		<!-- Featured Section: Conversation Persistence Mockups -->
		<Card class="bg-primary/5 border-primary/20">
			<CardContent class="p-6">
				<div class="flex items-center justify-between">
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<MessageSquare class="h-6 w-6 text-primary" />
							<h3 class="text-xl font-bold">Conversation Persistence Mockups</h3>
							<Badge variant="default">Phase 5</Badge>
						</div>
						<p class="text-sm text-muted-foreground">
							Interactive prototypes for conversation management UI patterns. Explore Card Grid, Compact List, and Timeline views with full session management features.
						</p>
					</div>
					<Button size="lg" onclick={() => window.location.href = '/gallery/conversations'}>
						View Mockups
						<ArrowRight class="h-4 w-4 ml-2" />
					</Button>
				</div>
			</CardContent>
		</Card>
		
		<!-- Featured Section: Phase 2 Planning Visualizations -->
		<Card class="bg-primary/5 border-primary/20">
			<CardContent class="p-6">
				<div class="flex items-center justify-between">
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<Code class="h-6 w-6 text-primary" />
							<h3 class="text-xl font-bold">Phase 2: Planning Visualization System</h3>
							<Badge variant="default">New</Badge>
						</div>
						<p class="text-sm text-muted-foreground">
							Interactive planning visualizations including PlanCanvas node-based graph, enhanced timeline with accordion, and Goal Context panel showing agent reasoning. Complete Phase 2 mock-ups ready for sign-off.
						</p>
					</div>
					<Button size="lg" onclick={() => window.location.href = '/gallery/plan'}>
						View Visualizations
						<ArrowRight class="h-4 w-4 ml-2" />
					</Button>
				</div>
			</CardContent>
		</Card>
		
		<!-- Featured Section: Knowledge Bank ---->
		<Card class="bg-primary/5 border-primary/20">
			<CardContent class="p-6">
				<div class="flex items-center justify-between">
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<Database class="h-6 w-6 text-primary" />
							<h3 class="text-xl font-bold">Knowledge Bank</h3>
							<Badge variant="default">New</Badge>
						</div>
						<p class="text-sm text-muted-foreground">
							Manage your indexed repositories and code search. View statistics, trigger reindexing, and configure semantic search settings for your workspace.
						</p>
					</div>
					<Button size="lg" onclick={() => window.location.href = '/kb'}>
						View Knowledge Bank
						<ArrowRight class="h-4 w-4 ml-2" />
					</Button>
				</div>
			</CardContent>
		</Card>
		
		<!-- Featured Section: User Profile ---->
		<Card class="bg-primary/5 border-primary/20">
			<CardContent class="p-6">
				<div class="flex items-center justify-between">
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<User class="h-6 w-6 text-primary" />
							<h3 class="text-xl font-bold">User Profile</h3>
						</div>
						<p class="text-sm text-muted-foreground">
							View your account information, usage statistics, and activity overview. Manage your Dolphin profile and preferences.
						</p>
					</div>
					<Button size="lg" onclick={() => window.location.href = '/profile'}>
						View Profile
						<ArrowRight class="h-4 w-4 ml-2" />
					</Button>
				</div>
			</CardContent>
		</Card>
		
		<!-- Featured Section: Settings ---->
		<Card class="bg-primary/5 border-primary/20">
			<CardContent class="p-6">
				<div class="flex items-center justify-between">
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<SettingsIcon class="h-6 w-6 text-primary" />
							<h3 class="text-xl font-bold">Settings</h3>
						</div>
						<p class="text-sm text-muted-foreground">
							Configure Dolphin preferences, AI model settings, API credentials, and notification preferences. Customize your development experience.
						</p>
					</div>
					<Button size="lg" onclick={() => window.location.href = '/settings'}>
						View Settings
						<ArrowRight class="h-4 w-4 ml-2" />
					</Button>
				</div>
			</CardContent>
		</Card>
	</div>
{/snippet}

{#snippet componentsSection()}
	<div class="space-y-12">
		<!-- Chat Components Section -->
		<section>
				<h2 class="text-2xl font-bold mb-6">Chat Components</h2>
				
				<div class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>MessageCard - User Message</CardTitle>
							<CardDescription>User messages with timestamp</CardDescription>
						</CardHeader>
						<CardContent>
							<MessageCard
								role="user"
								content="Can you help me refactor this function to use async/await?"
								timestamp="2:30 PM"
							/>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>MessageCard - Assistant Message</CardTitle>
							<CardDescription>AI assistant responses with streaming support</CardDescription>
						</CardHeader>
						<CardContent>
							<MessageCard
								role="assistant"
								content="I'll help you refactor that function. Let me analyze the code first and then propose a solution using async/await syntax."
								timestamp="2:31 PM"
							/>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>ChatInput</CardTitle>
							<CardDescription>Input field with send button and Cmd+Enter support</CardDescription>
						</CardHeader>
						<CardContent>
							<ChatInput onSend={handleSend} />
						</CardContent>
					</Card>
				</div>
			</section>

			<Separator />

			<!-- UI Components Section -->
			<section>
				<h2 class="text-2xl font-bold mb-6">UI Components</h2>
				
				<div class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>Tooltip</CardTitle>
							<CardDescription>Informative popup on hover</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="flex items-center gap-4">
								<Tooltip.Provider>
									<Tooltip.Root>
										<Tooltip.Trigger>
											<Button variant="outline" size="icon">
												<Info class="h-4 w-4" />
											</Button>
										</Tooltip.Trigger>
										<Tooltip.Content>
											<p>This is a helpful tooltip!</p>
										</Tooltip.Content>
									</Tooltip.Root>
								</Tooltip.Provider>
								<span class="text-sm text-muted-foreground">Hover over the icon</span>
							</div>
						</CardContent>
					</Card>
				</div>
			</section>

			<Separator />

			<!-- Tool Components Section -->
			<section>
				<h2 class="text-2xl font-bold mb-6">Tool Call Components</h2>
				
				<div class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>ToolCallCard - Running</CardTitle>
							<CardDescription>Tool execution in progress</CardDescription>
						</CardHeader>
						<CardContent>
							<ToolCallCard
								tool="search_knowledge"
								input={{ query: "authentication implementation", top_k: 5 }}
								status="running"
								collapsed={false}
							/>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>ToolCallCard - Success</CardTitle>
							<CardDescription>Completed tool execution with results</CardDescription>
						</CardHeader>
						<CardContent>
							<ToolCallCard
								tool="read_files"
								input={{ paths: ["src/auth.ts", "src/user.ts"] }}
								result={{ files: [{ path: "src/auth.ts", size_bytes: 2048 }], summary: { successful: 2, failed: 0 } }}
								status="success"
								executionTime={247}
								collapsed={false}
							/>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>ToolCallCard - Error</CardTitle>
							<CardDescription>Failed tool execution with error details</CardDescription>
						</CardHeader>
						<CardContent>
							<ToolCallCard
								tool="file_write"
								input={{ path: "src/config.ts", content: "export const config = {};" }}
								error="Permission denied: Cannot write to protected file"
								status="error"
								executionTime={12}
								collapsed={false}
							/>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>ToolCallCard - Failed Edit</CardTitle>
							<CardDescription>Tool execution with error state</CardDescription>
						</CardHeader>
						<CardContent>
							<ToolCallCard
								tool="apply_diff"
								input={{
									path: "src/routes/+page.svelte",
									diff: "@@ -1,5 +1,5 @@\n-const hello = \"world\";\n+const hello = \"dolphin\";"
								}}
								status="error"
								error="Failed to apply diff: Hunk #1 FAILED."
								executionTime={150}
								collapsed={false}
							/>
						</CardContent>
					</Card>
				</div>
			</section>

			<Separator />

			<!-- Advanced Components Section -->
			<section>
				<h2 class="text-2xl font-bold mb-6">Advanced Components</h2>
				
				<div class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>DiffViewer</CardTitle>
							<CardDescription>Collapsible diff viewer with rich visual information</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="diff-container">
								<DiffViewer
									diff={{
										oldFileName: 'src/components/utils.ts',
										newFileName: 'src/components/utils.ts',
										additions: 6,
										deletions: 1,
										hunks: [
											{
												oldStart: 1,
												oldLines: 8,
												newStart: 1,
												newLines: 13,
												lines: [
													' export function formatNumber(num: number): string {',
													'-  return num.toLocaleString();',
													'+  return new Intl.NumberFormat("en-US").format(num);',
													' }',
													' ',
													' export function cn(...inputs: string[]) {',
													'   return inputs.filter(Boolean).join(" ");',
													'+ }',
													'+',
													'+ export function debounce(func: Function, wait: number) {',
													'+   let timeout: NodeJS.Timeout;',
													'+   return (...args: any[]) => clearTimeout(timeout);',
													' }'
												]
											}
										]
									}}
									defaultExpanded={true}
								/>
							</div>
							
							<!-- Features List -->
							<div class="mt-6 text-sm text-muted-foreground space-y-2">
								<p class="font-semibold text-foreground">Features:</p>
								<ul class="list-disc list-inside space-y-1 text-xs">
									<li>Collapsible diff view with smooth animations</li>
									<li>Visual statistics bar showing additions vs deletions</li>
									<li>Dual line numbers (old/new) for precise navigation</li>
									<li>Syntax-aware highlighting for added/removed/context lines</li>
									<li>File metadata and change summary</li>
									<li>Sticky hunk headers for context</li>
								</ul>
							</div>
						</CardContent>
					</Card>
			
					<Card>
						<CardHeader>
							<CardTitle>PlanTimeline</CardTitle>
							<CardDescription>Horizontal scrollable timeline for multi-step plans</CardDescription>
						</CardHeader>
						<CardContent>
							<PlanTimeline steps={planSteps} />
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>ErrorAlert</CardTitle>
							<CardDescription>Error display with suggestions and retry capability</CardDescription>
						</CardHeader>
						<CardContent>
							{#if showErrorAlert}
								<ErrorAlert error={sampleError} onRetry={handleErrorRetry} />
							{:else}
								<Button onclick={() => showErrorAlert = true}>Show Error Alert</Button>
							{/if}
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>ConfirmDialog - Destructive Operation</CardTitle>
							<CardDescription>Modal dialog for confirming destructive operations</CardDescription>
						</CardHeader>
						<CardContent>
							<Button onclick={() => showConfirmDialog = true}>Show Confirmation Dialog</Button>
							
							{#if showConfirmDialog}
								<ConfirmDialog
									title="Destructive Operation"
									message="This command will delete all temporary files. This action cannot be undone."
									options={['Allow Once', 'Always Allow', 'Deny']}
									onSelect={handleConfirmSelect}
								/>
							{/if}
						</CardContent>
					</Card>
		
					<GalleryShowcase
						title="ConfirmDialog - Initialize Dolphin"
						description="First-time user setup dialog for workspace initialization"
					>
						{#snippet children()}
							<div class="space-y-4">
								<p class="text-sm text-muted-foreground mb-4">
									This dialog appears when users open the extension without a .dolphin configuration file.
								</p>
								
								<Button onclick={() => showInitDialog = true}>Show Initialize Dialog</Button>
								
								{#if showInitDialog}
									<ConfirmDialog
										title="Initialize Dolphin"
										message="Welcome to Dolphin! Would you like to initialize this workspace for semantic code search? This will create a .dolphin configuration file and start indexing your codebase."
										options={['Initialize Now', 'No Thanks']}
										onSelect={(choice) => {
											console.log('User chose:', choice);
											showInitDialog = false;
										}}
									/>
								{/if}
							</div>
						{/snippet}
					</GalleryShowcase>
				</div>
			</section>

			<Separator />
	
			<!-- Theme Testing Section -->
			<section>
				<h2 class="text-2xl font-bold mb-6">Theme & Styling</h2>
				
				<Card>
					<CardHeader>
						<CardTitle>Color Palette</CardTitle>
						<CardDescription>VS Code theme variables in use</CardDescription>
					</CardHeader>
					<CardContent>
						<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
							<div class="space-y-2">
								<div class="h-20 rounded bg-background border border-border"></div>
								<p class="text-xs text-center">Background</p>
							</div>
							<div class="space-y-2">
								<div class="h-20 rounded bg-foreground"></div>
								<p class="text-xs text-center">Foreground</p>
							</div>
							<div class="space-y-2">
								<div class="h-20 rounded bg-primary"></div>
								<p class="text-xs text-center">Primary</p>
							</div>
							<div class="space-y-2">
								<div class="h-20 rounded bg-secondary"></div>
								<p class="text-xs text-center">Secondary</p>
							</div>
							<div class="space-y-2">
								<div class="h-20 rounded bg-muted border border-border"></div>
								<p class="text-xs text-center">Muted</p>
							</div>
							<div class="space-y-2">
								<div class="h-20 rounded bg-accent"></div>
								<p class="text-xs text-center">Accent</p>
							</div>
							<div class="space-y-2">
								<div class="h-20 rounded bg-destructive"></div>
								<p class="text-xs text-center">Destructive</p>
							</div>
							<div class="space-y-2">
								<div class="h-20 rounded border-2 border-border bg-card"></div>
								<p class="text-xs text-center">Card</p>
							</div>
						</div>
					</CardContent>
				</Card>
			</section>
		</div>
{/snippet}
