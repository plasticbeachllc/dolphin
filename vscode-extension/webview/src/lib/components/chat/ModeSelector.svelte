<script lang="ts">
  import { Tabs, TabsList, TabsTrigger } from "$lib/components/ui/tabs";
  import { Code, Building2 } from "lucide-svelte";

  interface Props {
    value?: 'code' | 'architect';
    onValueChange?: (value: 'code' | 'architect') => void;
  }

  let { value = $bindable('code'), onValueChange }: Props = $props();

  function handleValueChange(newValue: string) {
    value = newValue as 'code' | 'architect';
    onValueChange?.(value);
  }
</script>

<div class="mode-selector">
  <Tabs value={value} onValueChange={handleValueChange}>
    <TabsList class="grid w-full grid-cols-2">
      <TabsTrigger value="code" class="flex items-center gap-2">
        <Code class="h-4 w-4" />
        <span>Code</span>
      </TabsTrigger>
      <TabsTrigger value="architect" class="flex items-center gap-2">
        <Building2 class="h-4 w-4" />
        <span>Architect</span>
      </TabsTrigger>
    </TabsList>
  </Tabs>
</div>

<style>
  .mode-selector {
    width: 100%;
    margin-bottom: 1rem;
  }
</style>
