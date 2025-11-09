<script lang="ts">
  import { Card, CardHeader, CardContent } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { AlertCircle, ChevronDown, ChevronUp } from 'lucide-svelte';
  import { slide } from 'svelte/transition';
  
  interface Props {
    error: {
      code: string;
      message: string;
      details?: string;
      suggestions?: string[];
      recoverable?: boolean;
    };
    onRetry?: () => void;
  }
  
  let { error, onRetry }: Props = $props();
  
  let showDetails = $state(false);
</script>

<Card class="error-alert border-destructive/50 bg-destructive/5">
  <CardHeader class="p-4">
    <div class="flex items-start gap-3">
      <AlertCircle class="h-5 w-5 text-destructive mt-0.5" />
      <div class="flex-1 min-w-0">
        <div class="flex items-center justify-between mb-1">
          <h4 class="font-semibold text-sm text-destructive">
            {error.code.replace(/_/g, ' ')}
          </h4>
          {#if error.details}
            <Button
              variant="ghost"
              size="sm"
              class="h-6 px-2"
              onclick={() => showDetails = !showDetails}
            >
              {#if showDetails}
                <ChevronUp class="h-4 w-4" />
              {:else}
                <ChevronDown class="h-4 w-4" />
              {/if}
              <span class="ml-1 text-xs">Details</span>
            </Button>
          {/if}
        </div>
        
        <p class="text-sm text-foreground mb-2">{error.message}</p>
        
        {#if error.suggestions && error.suggestions.length > 0}
          <div class="space-y-1">
            <p class="text-xs font-medium text-muted-foreground">Suggestions:</p>
            <ul class="list-disc list-inside space-y-1">
              {#each error.suggestions as suggestion}
                <li class="text-xs text-muted-foreground">{suggestion}</li>
              {/each}
            </ul>
          </div>
        {/if}
      </div>
    </div>
  </CardHeader>
  
  {#if showDetails && error.details}
  	<div transition:slide={{ duration: 200 }}>
  		<CardContent class="px-4 pb-4 pt-0">
  			<div class="bg-muted/50 rounded-md p-3">
  				<p class="text-xs font-mono text-muted-foreground whitespace-pre-wrap">
  					{error.details}
  				</p>
  			</div>
  		</CardContent>
  	</div>
  {/if}
  
  {#if error.recoverable && onRetry}
    <div class="px-4 pb-4">
      <Button
        variant="outline"
        size="sm"
        onclick={onRetry}
        class="w-full"
      >
        Try Again
      </Button>
    </div>
  {/if}
</Card>