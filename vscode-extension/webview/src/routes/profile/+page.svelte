<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { User, Mail, Calendar } from 'lucide-svelte';
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-4xl mx-auto">
		<div class="mb-8">
			<h1 class="text-3xl font-bold mb-2">User Profile</h1>
			<p class="text-muted-foreground">
				Your account information and usage statistics
			</p>
		</div>

		<div class="space-y-6">
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<User class="h-5 w-5" />
						Profile Information
					</CardTitle>
					<CardDescription>
						Your account details
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="flex items-center gap-3">
						<div class="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
							<User class="h-8 w-8 text-primary" />
						</div>
						<div>
							<p class="font-medium">Developer</p>
							<p class="text-sm text-muted-foreground">Local User</p>
						</div>
					</div>
					
					<div class="pt-4 space-y-3">
						<div class="flex items-center gap-3">
							<Mail class="h-4 w-4 text-muted-foreground" />
							<span class="text-sm">Not configured</span>
						</div>
						<div class="flex items-center gap-3">
							<Calendar class="h-4 w-4 text-muted-foreground" />
							<span class="text-sm">Active since: Today</span>
						</div>
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle>Usage Statistics</CardTitle>
					<CardDescription>
						Your activity overview (coming soon)
					</CardDescription>
				</CardHeader>
				<CardContent>
					<p class="text-sm text-muted-foreground">
						Usage tracking and statistics will be available in a future update.
					</p>
				</CardContent>
			</Card>
		</div>
	</div>
</div>