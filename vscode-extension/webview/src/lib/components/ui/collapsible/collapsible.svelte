<script lang="ts" module>
	import { Collapsible as CollapsiblePrimitive } from "bits-ui";
	
	const Root = CollapsiblePrimitive.Root;
	const Trigger = CollapsiblePrimitive.Trigger;
	const Content = CollapsiblePrimitive.Content;
</script>

<script lang="ts">
	import type { Snippet } from "svelte";
	
	let {
		open = $bindable(false),
		children
	}: {
		open?: boolean;
		children: Snippet;
	} = $props();
</script>

<CollapsiblePrimitive.Root bind:open>
	{@render children()}
</CollapsiblePrimitive.Root>