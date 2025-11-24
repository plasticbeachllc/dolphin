<script lang="ts">
  import { Badge } from '$lib/components/ui/badge';
  import { CheckCircle, Loader2, AlertCircle, Clock, XCircle } from 'lucide-svelte';
  import type { KBStatus } from '$lib/stores/kb-store';
  
  interface Props {
    status: KBStatus;
  }
  
  let { status }: Props = $props();
  
  type StatusConfig = {
    variant: 'default' | 'secondary' | 'destructive' | 'outline';
    icon: typeof CheckCircle;
    text: string;
    class: string;
  };

  const statusConfig: Record<KBStatus, StatusConfig> = {
    ready: {
      variant: 'default' as const,
      icon: CheckCircle,
      text: 'Ready',
      class: 'text-green-600 dark:text-green-400'
    },
    indexing: {
      variant: 'secondary' as const,
      icon: Loader2,
      text: 'Indexing',
      class: 'text-blue-600 dark:text-blue-400 animate-spin'
    },
    reindexing: {
      variant: 'secondary' as const,
      icon: Loader2,
      text: 'Reindexing',
      class: 'text-blue-600 dark:text-blue-400 animate-spin'
    },
    offline: {
      variant: 'destructive' as const,
      icon: XCircle,
      text: 'Offline',
      class: 'text-red-600 dark:text-red-400'
    },
    stale: {
      variant: 'outline' as const,
      icon: Clock,
      text: 'Needs Update',
      class: 'text-yellow-600 dark:text-yellow-400'
    },
    error: {
      variant: 'destructive' as const,
      icon: AlertCircle,
      text: 'Error',
      class: 'text-red-600 dark:text-red-400'
    }
  };

  const config = $derived(statusConfig[status]);
  const IconComponent = $derived(config.icon);
</script>

<Badge variant={config.variant}>
  <IconComponent class="mr-1.5 h-3.5 w-3.5 {config.class}" />
  {config.text}
</Badge>
