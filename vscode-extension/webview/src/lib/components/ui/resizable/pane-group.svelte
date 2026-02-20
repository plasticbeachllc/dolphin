<script lang="ts">
	import { PaneGroup, type PaneGroupProps } from "paneforge";
	import { cn } from "$lib/utils.js";

	type $$Props = PaneGroupProps & { direction: PaneGroupProps["direction"] };

	let className: $$Props["class"] = undefined;
	export { className as class };
	export let direction: $$Props["direction"] = "horizontal";

	// Relax typing to avoid svelte2tsx constructor constraints
	const PaneGroupComponent: any = PaneGroup;
</script>

<PaneGroupComponent
	class={cn("flex h-full w-full data-[direction=vertical]:flex-col", className)}
	{direction}
	{...$$restProps}
	let:isDragging
>
	<slot {isDragging} />
</PaneGroupComponent>
