<script lang="ts">
	import { PaneResizer, type PaneResizerProps } from "paneforge";
	import { GripVertical } from "lucide-svelte";
	import { cn } from "$lib/utils.js";

	type $$Props = PaneResizerProps & {
		withHandle?: boolean;
	};

	let className: $$Props["class"] = undefined;
	export { className as class };
	export let withHandle: $$Props["withHandle"] = false;
</script>

<PaneResizer
	class={cn(
		"bg-border relative flex w-px items-center justify-center after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 data-[direction=vertical]:h-px data-[direction=vertical]:w-full data-[direction=vertical]:after:left-0 data-[direction=vertical]:after:h-1 data-[direction=vertical]:after:w-full data-[direction=vertical]:after:-translate-y-1/2 data-[direction=vertical]:after:translate-x-0 [&[data-direction=vertical]>div]:rotate-90",
		className
	)}
	{...$$restProps}
>
	{#if withHandle}
		<div
			class="bg-border z-10 flex h-4 w-3 items-center justify-center rounded-sm border"
		>
			<GripVertical class="h-2.5 w-2.5" />
		</div>
	{/if}
</PaneResizer>
