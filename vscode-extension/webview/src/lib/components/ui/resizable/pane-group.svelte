<script lang="ts">
	import { PaneGroup as PaneGroupPrimitive } from "paneforge";
	import { cn } from "$lib/utils.js";

	type $$Props = PaneGroupPrimitive.Props;

	let className: $$Props["class"] = undefined;
	export { className as class };
</script>

<PaneGroupPrimitive.Root
	class={cn("flex h-full w-full data-[direction=vertical]:flex-col", className)}
	{...$$restProps}
	let:isDragging
>
	<slot {isDragging} />
</PaneGroupPrimitive.Root>
