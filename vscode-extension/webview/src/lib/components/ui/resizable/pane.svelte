<script lang="ts">
	import { Pane as PanePrimitive } from "paneforge";

	type $$Props = PanePrimitive.Props;
</script>

<PanePrimitive.Root {...$$restProps}>
	<slot />
</PanePrimitive.Root>
