<script lang="ts">
	import '$lib/assets/favicon.svg';
	import '../app.css';
	import AppNavigation from '$lib/components/navigation/AppNavigation.svelte';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';

	let { children } = $props();

	function handleNavigate(path: string) {
		// Handle navigation - in webview context, this would communicate with VS Code extension
		// For now, we'll use SvelteKit's built-in navigation
		if (typeof window !== 'undefined') {
			window.history.pushState({}, '', path);
		}
	}

	onMount(() => {
		// Apply dark mode class to root element
		document.documentElement.classList.add('dark');
	});
</script>

<div class="flex h-screen flex-col bg-background text-foreground">
	<AppNavigation currentPath={$page.url.pathname} onNavigate={handleNavigate} />
	<div class="flex-1 overflow-hidden bg-background">
		{@render children()}
	</div>
</div>