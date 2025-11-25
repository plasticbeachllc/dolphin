<script lang="ts">
	import { Tooltip as TooltipPrimitive } from "bits-ui";

	let {
		ref = $bindable(null),
		child = undefined,
		children = undefined,
		...restProps
	}: TooltipPrimitive.TriggerProps = $props();

	// Forward default slot as `child` so Bits UI renders it without wrapping in its own <button>
	// Avoid complex union inference from Bits UI child/children typings
	const forwardedChild = $derived((child ?? children) as typeof child);
</script>

<TooltipPrimitive.Trigger
	bind:ref
	data-slot="tooltip-trigger"
	child={forwardedChild}
	children={undefined}
	{...restProps}
/>
