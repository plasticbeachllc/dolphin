<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Settings, Zap, Database, Bell } from 'lucide-svelte';
	import AuthStatus from '$lib/components/AuthStatus.svelte';

	let apiKey = $state('');
	let model = $state('claude-sonnet-4');
	let temperature = $state(0.7);
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-4xl mx-auto">
		<div class="mb-8">
			<h1 class="text-3xl font-bold mb-2">Settings</h1>
			<p class="text-muted-foreground">
				Configure Dolphin preferences and API connections
			</p>
		</div>

		<div class="space-y-6">
			<!-- Authentication Status -->
			<AuthStatus />

			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Zap class="h-5 w-5" />
						AI Model Configuration
					</CardTitle>
					<CardDescription>
						Configure your AI model preferences and API credentials
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div>
						<label for="api-key" class="text-sm font-medium mb-2 block">
							API Key
						</label>
						<Input
							id="api-key"
							type="password"
							bind:value={apiKey}
							placeholder="Enter your Anthropic API key"
						/>
					</div>

					<div>
						<label for="model" class="text-sm font-medium mb-2 block">
							Model
						</label>
						<Input
							id="model"
							bind:value={model}
							placeholder="claude-sonnet-4"
						/>
					</div>

					<div>
						<label for="temperature" class="text-sm font-medium mb-2 block">
							Temperature: {temperature}
						</label>
						<input
							id="temperature"
							type="range"
							min="0"
							max="1"
							step="0.1"
							bind:value={temperature}
							class="w-full"
						/>
						<p class="text-xs text-muted-foreground mt-1">
							Lower values make responses more focused, higher values more creative
						</p>
					</div>

					<Button class="w-full">Save Configuration</Button>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Database class="h-5 w-5" />
						Knowledge Bank
					</CardTitle>
					<CardDescription>
						Manage your indexed repositories and code search
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<p class="text-sm text-muted-foreground">
						Knowledge Bank is running and indexing your workspace
					</p>
					<div class="flex gap-2">
						<Button variant="outline" class="flex-1">Reindex</Button>
						<Button variant="outline" class="flex-1">View Stats</Button>
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Bell class="h-5 w-5" />
						Notifications
					</CardTitle>
					<CardDescription>
						Control notification preferences
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<label class="flex items-center gap-2 cursor-pointer">
						<input type="checkbox" checked class="rounded" />
						<span class="text-sm">Show completion notifications</span>
					</label>
					<label class="flex items-center gap-2 cursor-pointer">
						<input type="checkbox" checked class="rounded" />
						<span class="text-sm">Confirm destructive operations</span>
					</label>
					<label class="flex items-center gap-2 cursor-pointer">
						<input type="checkbox" class="rounded" />
						<span class="text-sm">Enable sound effects</span>
					</label>
				</CardContent>
			</Card>
		</div>
	</div>
</div>