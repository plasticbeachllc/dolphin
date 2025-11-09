<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import MessageCard from '$lib/components/chat/MessageCard.svelte';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import ToolCallCard from '$lib/components/tools/ToolCallCard.svelte';
	import DiffViewer from '$lib/components/DiffViewer.svelte';
	import PlanTimeline from '$lib/components/PlanTimeline.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import ErrorAlert from '$lib/components/ErrorAlert.svelte';
	
	// Sample data
	let showConfirmDialog = $state(false);
	let showErrorAlert = $state(true);
	
	const sampleDiff = `diff --git a/src/example.ts b/src/example.ts
index 1234567..abcdefg 100644
--- a/src/example.ts
+++ b/src/example.ts
@@ -1,3 +1,4 @@
 function hello(name: string) {
-  console.log("Hello " + name);
+  console.log(\`Hello \${name}\`);
+  return \`Greeting: \${name}\`;
 }`;

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
	
	function handleDiffApprove() {
		console.log('Diff approved');
	}
	
	function handleDiffReject(feedback?: string) {
		console.log('Diff rejected:', feedback);
	}
	
	function handleConfirmSelect(choice: string) {
		console.log('Confirmation choice:', choice);
		showConfirmDialog = false;
	}
	
	function handleErrorRetry() {
		console.log('Retrying operation');
	}
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-6xl mx-auto">
		<div class="mb-8">
			<h1 class="text-4xl font-bold mb-2">Component Gallery</h1>
			<p class="text-muted-foreground">
				Visual showcase of all Dolphin UI components with interactive examples
			</p>
		</div>

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
							<CardDescription>Code diff viewer with approve/reject actions</CardDescription>
						</CardHeader>
						<CardContent>
							<DiffViewer
								diffContent={sampleDiff}
								onApprove={handleDiffApprove}
								onReject={handleDiffReject}
							/>
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
							<CardTitle>ConfirmDialog</CardTitle>
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
				</div>
			</section>

			<Separator />

			<!-- Agentic Animations Section -->
			<section>
				<h2 class="text-2xl font-bold mb-6">Agentic Animations</h2>

				<div class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>Thinking Indicator</CardTitle>
							<CardDescription>Shows when the agent is processing</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="flex items-center gap-3 p-4 bg-muted rounded-lg">
								<div class="w-8 h-8 rounded-full bg-primary animate-pulse-glow flex items-center justify-center text-primary-foreground text-xs">
									AI
								</div>
								<div class="flex gap-1">
									<div class="w-2 h-2 rounded-full bg-foreground animate-typing-dot"></div>
									<div class="w-2 h-2 rounded-full bg-foreground animate-typing-dot"></div>
									<div class="w-2 h-2 rounded-full bg-foreground animate-typing-dot"></div>
								</div>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Message Slide In</CardTitle>
							<CardDescription>Smooth entrance animation for new messages</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="p-4 bg-card border rounded-lg animate-slide-in-up">
								<p class="text-sm">This message slides in smoothly from below</p>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Loading Shimmer</CardTitle>
							<CardDescription>Skeleton loading state</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="h-16 rounded-lg animate-shimmer"></div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Active Status</CardTitle>
							<CardDescription>Breathing indicator for active agents</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="flex items-center gap-2">
								<div class="w-3 h-3 rounded-full bg-green-500 animate-breathe"></div>
								<p class="text-sm text-muted-foreground">Agent is active</p>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Fade In</CardTitle>
							<CardDescription>Gentle reveal animation</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="p-4 bg-accent rounded-lg animate-fade-in">
								<p class="text-sm">This content fades in gracefully</p>
							</div>
						</CardContent>
					</Card>

					<Card>
						<CardHeader>
							<CardTitle>Attention Bounce</CardTitle>
							<CardDescription>Subtle bounce for notifications</CardDescription>
						</CardHeader>
						<CardContent>
							<span class="inline-flex px-3 py-1 rounded-full text-xs font-medium bg-primary text-primary-foreground animate-bounce-subtle">
								New
							</span>
						</CardContent>
					</Card>
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
	</div>
</div>