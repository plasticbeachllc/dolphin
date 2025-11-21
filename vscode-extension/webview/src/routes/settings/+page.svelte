<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Database, Bell } from 'lucide-svelte';
	import AuthStatus from '$lib/components/AuthStatus.svelte';
	import ProviderSelection from '$lib/components/ProviderSelection.svelte';
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
			<!-- Provider Selection -->
			<ProviderSelection />

			<!-- Authentication Status -->
			<AuthStatus />

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