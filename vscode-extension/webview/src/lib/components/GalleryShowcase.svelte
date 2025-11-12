<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	
	let {
		title,
		description,
		children
	}: {
		title: string;
		description: string;
		children: any;
	} = $props();
	
	let resetKey = $state(0);
	
	function reset() {
		resetKey += 1;
	}
</script>

<Card>
	<CardHeader>
		<div class="flex items-start justify-between">
			<div class="flex-1">
				<CardTitle>{title}</CardTitle>
				<CardDescription>{description}</CardDescription>
			</div>
			<Button onclick={reset} variant="ghost" size="sm" class="ml-2" aria-label="Reset showcase">
				<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
				</svg>
			</Button>
		</div>
	</CardHeader>
	<CardContent>
		{#key resetKey}
			{@render children()}
		{/key}
	</CardContent>
</Card>