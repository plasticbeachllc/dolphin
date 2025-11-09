<script lang="ts">
	import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { FileText } from 'lucide-svelte';
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-4xl mx-auto">
		<div class="mb-8">
			<h1 class="text-3xl font-bold mb-2">Documentation Generator</h1>
			<p class="text-muted-foreground">
				Automatically generate comprehensive documentation for your codebase
			</p>
		</div>

		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<FileText class="h-5 w-5" />
					Documentation Tools
				</CardTitle>
				<CardDescription>
					AI-powered documentation generation and updates
				</CardDescription>
			</CardHeader>
			<CardContent>
				<p class="text-sm text-muted-foreground">
					This feature is coming soon. It will help you generate:
				</p>
				<ul class="mt-4 space-y-2 text-sm text-muted-foreground">
					<li>• API documentation from code</li>
					<li>• README files for projects</li>
					<li>• Inline code comments</li>
					<li>• Architecture diagrams</li>
				</ul>
			</CardContent>
		</Card>
	</div>
</div>