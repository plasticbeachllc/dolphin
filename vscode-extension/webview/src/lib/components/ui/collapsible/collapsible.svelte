

<script lang="ts">
	import type { Snippet } from "svelte";
	import { Collapsible as CollapsiblePrimitive } from "bits-ui";

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