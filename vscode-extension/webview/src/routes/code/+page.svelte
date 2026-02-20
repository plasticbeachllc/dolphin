<script lang="ts">
	import { Card, CardHeader, CardContent, CardDescription, CardTitle } from '$lib/components/ui/card';
	import { Code2, FileCode, GitBranch } from 'lucide-svelte';
</script>

<div class="h-full overflow-auto p-6">
	<div class="max-w-4xl mx-auto">
		<div class="mb-8">
			<h1 class="text-3xl font-bold mb-2">Code Assistant</h1>
			<p class="text-muted-foreground">
				AI-powered code review, refactoring, and analysis tools
			</p>
		</div>

		<div class="grid gap-6 md:grid-cols-2">
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Code2 class="h-5 w-5" />
						Code Review
					</CardTitle>
					<CardDescription>
						Get intelligent code review suggestions and best practice recommendations
					</CardDescription>
				</CardHeader>
				<CardContent>
					<p class="text-sm text-muted-foreground">
						Upload code snippets or select files for automated review with actionable feedback.
					</p>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<FileCode class="h-5 w-5" />
						Refactoring
					</CardTitle>
					<CardDescription>
						Intelligent code refactoring with safety guarantees
					</CardDescription>
				</CardHeader>
				<CardContent>
					<p class="text-sm text-muted-foreground">
						Automatically identify and apply refactoring patterns to improve code quality.
					</p>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<GitBranch class="h-5 w-5" />
						Debugging Assistant
					</CardTitle>
					<CardDescription>
						AI-assisted debugging and error analysis
					</CardDescription>
				</CardHeader>
				<CardContent>
					<p class="text-sm text-muted-foreground">
						Analyze stack traces and logs to quickly identify root causes and suggest fixes.
					</p>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle>Coming Soon</CardTitle>
					<CardDescription>
						More code tools in development
					</CardDescription>
				</CardHeader>
				<CardContent>
					<ul class="text-sm text-muted-foreground space-y-1">
						<li>• Performance optimization</li>
						<li>• Security scanning</li>
						<li>• Dependency analysis</li>
					</ul>
				</CardContent>
			</Card>
		</div>
	</div>
</div>