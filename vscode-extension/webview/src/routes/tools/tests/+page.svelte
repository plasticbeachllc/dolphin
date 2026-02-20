<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { TestTube } from 'lucide-svelte';
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-4xl mx-auto">
		<div class="mb-8">
			<h1 class="text-3xl font-bold mb-2">Test Generator</h1>
			<p class="text-muted-foreground">
				Automatically generate comprehensive test suites for your code
			</p>
		</div>

		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<TestTube class="h-5 w-5" />
					Test Generation
				</CardTitle>
				<CardDescription>
					AI-powered test case generation
				</CardDescription>
			</CardHeader>
			<CardContent>
				<p class="text-sm text-muted-foreground">
					This feature is coming soon. It will help you:
				</p>
				<ul class="mt-4 space-y-2 text-sm text-muted-foreground">
					<li>• Generate unit tests automatically</li>
					<li>• Create integration test scenarios</li>
					<li>• Build edge case test coverage</li>
					<li>• Generate test data and fixtures</li>
					<li>• Suggest assertion improvements</li>
				</ul>
			</CardContent>
		</Card>
	</div>
</div>