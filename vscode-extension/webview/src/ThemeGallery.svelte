<script lang="ts">
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Collapsible from '$lib/components/ui/collapsible';
	import { Input } from '$lib/components/ui/input';
	import { SendHorizontal, Square } from 'lucide-svelte';

	let themes = [
		{ name: 'Neutral (Default)', class: '' },
		{ name: 'Dark', class: 'dark' },
		{ name: 'Zinc', class: 'theme-zinc' },
		{ name: 'Slate', class: 'theme-slate' },
		{ name: 'Stone', class: 'theme-stone' },
		{ name: 'Gray', class: 'theme-gray' }
	];

	let selectedTheme = $state('dark');
	let isProcessing = $state(false);

	function applyTheme(themeClass: string) {
		document.documentElement.className = themeClass;
		selectedTheme = themeClass;
	}
	
	function toggleProcessing() {
		isProcessing = !isProcessing;
	}
</script>

<div class="min-h-screen bg-background p-8">
	<div class="max-w-6xl mx-auto space-y-8">
		<div class="space-y-4">
			<h1 class="text-4xl font-bold text-foreground">Dolphin Theme Gallery</h1>
			<p class="text-muted-foreground">Select a theme to preview the UI components</p>
			
			<div class="flex gap-2 flex-wrap">
				{#each themes as theme}
					<Button
						variant={selectedTheme === theme.class ? 'default' : 'outline'}
						onclick={() => applyTheme(theme.class)}
					>
						{theme.name}
					</Button>
				{/each}
			</div>
		</div>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
			<!-- Chat Message Card -->
			<Card>
				<CardHeader>
					<CardTitle>Chat Message</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="flex items-start gap-3">
						<div class="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center">
							U
						</div>
						<div class="flex-1 space-y-1">
							<p class="text-sm font-medium text-foreground">User</p>
							<p class="text-sm text-foreground">How do I implement dark mode in Svelte?</p>
						</div>
					</div>

					<div class="flex items-start gap-3">
						<div class="w-8 h-8 rounded-full bg-secondary text-secondary-foreground flex items-center justify-center">
							A
						</div>
						<div class="flex-1 space-y-1">
							<p class="text-sm font-medium text-foreground">Assistant</p>
							<p class="text-sm text-foreground">
								You can use mode-watcher or add a dark class to your root element.
							</p>
						</div>
					</div>
				</CardContent>
			</Card>

			<!-- Tool Call Card -->
			<Card>
				<CardHeader>
					<CardTitle>Tool Call</CardTitle>
				</CardHeader>
				<CardContent>
					<Collapsible.Root>
						<div class="flex items-center justify-between">
							<div class="flex items-center gap-2">
								<Badge variant="outline">execute_command</Badge>
								<Badge>success</Badge>
							</div>
							<Collapsible.Trigger asChild let:builder>
								<Button builders={[builder]} variant="ghost" size="sm">
									Toggle
								</Button>
							</Collapsible.Trigger>
						</div>
						<Collapsible.Content class="mt-4">
							<div class="rounded-md border border-border bg-muted p-4">
								<p class="text-sm font-mono text-muted-foreground">
									$ npm run build
								</p>
							</div>
						</Collapsible.Content>
					</Collapsible.Root>
				</CardContent>
			</Card>

			<!-- Input Component -->
			<Card>
				<CardHeader>
					<CardTitle>Chat Input with Send/Stop Button</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="flex gap-2">
						<Input placeholder="Type your message..." class="flex-1" disabled={isProcessing} />
						<Button
							onclick={toggleProcessing}
							variant={isProcessing ? 'destructive' : 'default'}
							size="icon"
							aria-label={isProcessing ? 'Stop' : 'Send'}
						>
							{#if isProcessing}
								<Square class="h-4 w-4" />
							{:else}
								<SendHorizontal class="h-4 w-4" />
							{/if}
						</Button>
					</div>
					<p class="text-xs text-muted-foreground">
						{isProcessing ? 'Click square to stop generation' : 'Click arrow to send message'}
					</p>
				</CardContent>
			</Card>

			<!-- Badges & States -->
			<Card>
				<CardHeader>
					<CardTitle>Badges & States</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="flex gap-2 flex-wrap">
						<Badge>Default</Badge>
						<Badge variant="secondary">Secondary</Badge>
						<Badge variant="outline">Outline</Badge>
						<Badge variant="destructive">Error</Badge>
					</div>
					<div class="flex gap-2 flex-wrap">
						<Button>Primary</Button>
						<Button variant="secondary">Secondary</Button>
						<Button variant="outline">Outline</Button>
						<Button variant="ghost">Ghost</Button>
					</div>
				</CardContent>
			</Card>

			<!-- Background Colors -->
			<Card>
				<CardHeader>
					<CardTitle>Background Colors</CardTitle>
				</CardHeader>
				<CardContent class="space-y-2">
					<div class="p-4 rounded bg-background border border-border">
						<p class="text-sm">Background: <code class="text-xs">bg-background</code></p>
					</div>
					<div class="p-4 rounded bg-card border border-border">
						<p class="text-sm">Card: <code class="text-xs">bg-card</code></p>
					</div>
					<div class="p-4 rounded bg-muted">
						<p class="text-sm">Muted: <code class="text-xs">bg-muted</code></p>
					</div>
					<div class="p-4 rounded bg-accent">
						<p class="text-sm">Accent: <code class="text-xs">bg-accent</code></p>
					</div>
				</CardContent>
			</Card>

			<!-- Text Colors -->
			<Card>
				<CardHeader>
					<CardTitle>Text Colors</CardTitle>
				</CardHeader>
				<CardContent class="space-y-2">
					<p class="text-foreground">Foreground: The quick brown fox</p>
					<p class="text-muted-foreground">Muted Foreground: The quick brown fox</p>
					<p class="text-primary">Primary: The quick brown fox</p>
					<p class="text-secondary-foreground">Secondary Foreground: The quick brown fox</p>
					<p class="text-destructive">Destructive: The quick brown fox</p>
				</CardContent>
			</Card>
		</div>

		<!-- Agentic Animations -->
		<Card class="md:col-span-2">
			<CardHeader>
				<CardTitle>Agentic Animations</CardTitle>
			</CardHeader>
			<CardContent class="space-y-6">
				<!-- Thinking/Processing -->
				<div class="space-y-2">
					<p class="text-sm font-medium">Thinking Indicator</p>
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
				</div>

				<!-- Message Slide In -->
				<div class="space-y-2">
					<p class="text-sm font-medium">Message Slide In</p>
					<div class="p-4 bg-card border rounded-lg animate-slide-in-up">
						<p class="text-sm">This message slides in smoothly</p>
					</div>
				</div>

				<!-- Shimmer Loading -->
				<div class="space-y-2">
					<p class="text-sm font-medium">Loading Shimmer</p>
					<div class="h-16 rounded-lg animate-shimmer"></div>
				</div>

				<!-- Breathing Status -->
				<div class="space-y-2">
					<p class="text-sm font-medium">Active Status</p>
					<div class="flex items-center gap-2">
						<div class="w-3 h-3 rounded-full bg-green-500 animate-breathe"></div>
						<p class="text-sm text-muted-foreground">Agent is active</p>
					</div>
				</div>

				<!-- Fade In -->
				<div class="space-y-2">
					<p class="text-sm font-medium">Fade In</p>
					<div class="p-4 bg-accent rounded-lg animate-fade-in">
						<p class="text-sm">Gentle fade in effect</p>
					</div>
				</div>

				<!-- Bounce Attention -->
				<div class="space-y-2">
					<p class="text-sm font-medium">Attention Bounce</p>
					<Badge class="animate-bounce-subtle">New</Badge>
				</div>
			</CardContent>
		</Card>

		<!-- CSS Variables Reference -->
		<Card>
			<CardHeader>
				<CardTitle>Current CSS Variables</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="grid grid-cols-2 md:grid-cols-3 gap-4 font-mono text-xs">
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--background)"></div>
						<p class="text-muted-foreground">--background</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--foreground)"></div>
						<p class="text-muted-foreground">--foreground</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--card)"></div>
						<p class="text-muted-foreground">--card</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--primary)"></div>
						<p class="text-muted-foreground">--primary</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--secondary)"></div>
						<p class="text-muted-foreground">--secondary</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--muted)"></div>
						<p class="text-muted-foreground">--muted</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--accent)"></div>
						<p class="text-muted-foreground">--accent</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1 border" style="background-color: var(--border)"></div>
						<p class="text-muted-foreground">--border</p>
					</div>
					<div>
						<div class="w-full h-8 rounded mb-1" style="background-color: var(--destructive)"></div>
						<p class="text-muted-foreground">--destructive</p>
					</div>
				</div>
			</CardContent>
		</Card>
	</div>
</div>