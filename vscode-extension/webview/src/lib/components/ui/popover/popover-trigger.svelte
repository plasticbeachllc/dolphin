<script lang="ts">
	import { cn } from "$lib/utils.js";
	import { Popover as PopoverPrimitive } from "bits-ui";

	let {
		ref = $bindable(null),
		class: className,
		child = undefined,
		children = undefined,
		...restProps
	}: PopoverPrimitive.TriggerProps = $props();

	// Avoid complex union inference from Bits UI child/children typings
	const forwardedChild = $derived((child ?? children) as typeof child);
</script>

<PopoverPrimitive.Trigger
	bind:ref
	data-slot="popover-trigger"
	class={cn("", className)}
	child={forwardedChild}
	children={undefined}
	{...restProps}
/>
