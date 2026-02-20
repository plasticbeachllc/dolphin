<script lang="ts">
  import KBManagementPanel from '$lib/components/kb/KBManagementPanel.svelte';
</script>

<div class="p-6 max-w-2xl mx-auto">
  <div class="space-y-6">
    <div>
      <h1 class="text-2xl font-bold mb-2">Knowledge Base</h1>
      <p class="text-sm text-muted-foreground">
        Manage your workspace code index for semantic search and AI-powered features.
      </p>
    </div>

    <KBManagementPanel />
  </div>
</div>