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
	<main class="flex-1 overflow-hidden bg-background">
		{@render children()}
	</main>
	<!-- Live region for screen reader announcements - WCAG 2.1 AA compliance -->
	<div
		id="a11y-announcer"
		role="status"
		aria-live="polite"
		aria-atomic="true"
		class="sr-only"
	></div>
</div>