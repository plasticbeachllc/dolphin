<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Separator } from "$lib/components/ui/separator";
  import { RotateCcw } from "lucide-svelte";
  
  /**
   * AnimationGallery - Showcase of all animation patterns with individual reset controls
   */
  
  // Animation reset keys to force re-renders
  let thinkingKey = $state(0);
  let slideInKey = $state(0);
  let shimmerKey = $state(0);
  let breatheKey = $state(0);
  let fadeInKey = $state(0);
  let bounceKey = $state(0);
  
  function resetThinking() {
    thinkingKey++;
  }
  
  function resetSlideIn() {
    slideInKey++;
  }
  
  function resetShimmer() {
    shimmerKey++;
  }
  
  function resetBreathe() {
    breatheKey++;
  }
  
  function resetFadeIn() {
    fadeInKey++;
  }
  
  function resetBounce() {
    bounceKey++;
  }
</script>

<div class="space-y-8 p-6">
  <div class="space-y-2">
    <h2 class="text-2xl font-bold">Animation Library</h2>
    <p class="text-sm text-muted-foreground">
      Reusable animation patterns for creating delightful interactions
    </p>
  </div>

  <Separator />

  <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <!-- Thinking Indicator -->
    <Card.Root>
      <Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <Card.Title class="text-base">Thinking Indicator</Card.Title>
          <Card.Description class="text-xs">Shows when the agent is processing</Card.Description>
        </div>
        <Button variant="ghost" size="icon" onclick={resetThinking}>
          <RotateCcw class="h-4 w-4" />
        </Button>
      </Card.Header>
      <Card.Content>
        {#key thinkingKey}
          <div class="flex items-center gap-3 p-6 bg-muted rounded-lg">
            <div class="w-8 h-8 rounded-full bg-primary animate-pulse-glow flex items-center justify-center text-primary-foreground text-xs font-semibold">
              AI
            </div>
            <div class="flex gap-1">
              <div class="w-2 h-2 rounded-full bg-foreground animate-typing-dot"></div>
              <div class="w-2 h-2 rounded-full bg-foreground animate-typing-dot"></div>
              <div class="w-2 h-2 rounded-full bg-foreground animate-typing-dot"></div>
            </div>
          </div>
        {/key}
        <div class="mt-3 text-xs text-muted-foreground">
          <code class="bg-muted px-2 py-1 rounded">animate-pulse-glow</code> + 
          <code class="bg-muted px-2 py-1 rounded">animate-typing-dot</code>
        </div>
      </Card.Content>
    </Card.Root>

    <!-- Message Slide In -->
    <Card.Root>
      <Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <Card.Title class="text-base">Message Slide In</Card.Title>
          <Card.Description class="text-xs">Smooth entrance animation for new messages</Card.Description>
        </div>
        <Button variant="ghost" size="icon" onclick={resetSlideIn}>
          <RotateCcw class="h-4 w-4" />
        </Button>
      </Card.Header>
      <Card.Content>
        {#key slideInKey}
          <div class="p-4 bg-card border rounded-lg animate-slide-in-up">
            <p class="text-sm">This message slides in smoothly from below</p>
          </div>
        {/key}
        <div class="mt-3 text-xs text-muted-foreground">
          <code class="bg-muted px-2 py-1 rounded">animate-slide-in-up</code>
        </div>
      </Card.Content>
    </Card.Root>

    <!-- Loading Shimmer -->
    <Card.Root>
      <Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <Card.Title class="text-base">Loading Shimmer</Card.Title>
          <Card.Description class="text-xs">Skeleton loading state with shimmer effect</Card.Description>
        </div>
        <Button variant="ghost" size="icon" onclick={resetShimmer}>
          <RotateCcw class="h-4 w-4" />
        </Button>
      </Card.Header>
      <Card.Content>
        {#key shimmerKey}
          <div class="space-y-3">
            <div class="h-4 rounded animate-shimmer"></div>
            <div class="h-4 rounded animate-shimmer w-5/6"></div>
            <div class="h-4 rounded animate-shimmer w-4/6"></div>
          </div>
        {/key}
        <div class="mt-3 text-xs text-muted-foreground">
          <code class="bg-muted px-2 py-1 rounded">animate-shimmer</code>
        </div>
      </Card.Content>
    </Card.Root>

    <!-- Active Status -->
    <Card.Root>
      <Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <Card.Title class="text-base">Active Status</Card.Title>
          <Card.Description class="text-xs">Breathing indicator for active agents</Card.Description>
        </div>
        <Button variant="ghost" size="icon" onclick={resetBreathe}>
          <RotateCcw class="h-4 w-4" />
        </Button>
      </Card.Header>
      <Card.Content>
        {#key breatheKey}
          <div class="flex items-center gap-2 p-4">
            <div class="w-3 h-3 rounded-full bg-green-500 animate-breathe"></div>
            <p class="text-sm text-muted-foreground">Agent is active</p>
          </div>
        {/key}
        <div class="mt-3 text-xs text-muted-foreground">
          <code class="bg-muted px-2 py-1 rounded">animate-breathe</code>
        </div>
      </Card.Content>
    </Card.Root>

    <!-- Fade In -->
    <Card.Root>
      <Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <Card.Title class="text-base">Fade In</Card.Title>
          <Card.Description class="text-xs">Gentle reveal animation</Card.Description>
        </div>
        <Button variant="ghost" size="icon" onclick={resetFadeIn}>
          <RotateCcw class="h-4 w-4" />
        </Button>
      </Card.Header>
      <Card.Content>
        {#key fadeInKey}
          <div class="p-4 bg-accent rounded-lg animate-fade-in">
            <p class="text-sm">This content fades in gracefully</p>
          </div>
        {/key}
        <div class="mt-3 text-xs text-muted-foreground">
          <code class="bg-muted px-2 py-1 rounded">animate-fade-in</code>
        </div>
      </Card.Content>
    </Card.Root>

    <!-- Attention Bounce -->
    <Card.Root>
      <Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <Card.Title class="text-base">Attention Bounce</Card.Title>
          <Card.Description class="text-xs">Subtle bounce for notifications</Card.Description>
        </div>
        <Button variant="ghost" size="icon" onclick={resetBounce}>
          <RotateCcw class="h-4 w-4" />
        </Button>
      </Card.Header>
      <Card.Content>
        {#key bounceKey}
          <div class="p-4">
            <span class="inline-flex px-3 py-1 rounded-full text-xs font-medium bg-primary text-primary-foreground animate-bounce-subtle">
              New
            </span>
          </div>
        {/key}
        <div class="mt-3 text-xs text-muted-foreground">
          <code class="bg-muted px-2 py-1 rounded">animate-bounce-subtle</code>
        </div>
      </Card.Content>
    </Card.Root>
  </div>

  <Separator />

  <!-- Usage Guidelines -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Animation Guidelines</h3>
      <p class="text-sm text-muted-foreground">Best practices for using animations</p>
    </div>
    
    <Card.Root>
      <Card.Content class="pt-6">
        <div class="grid md:grid-cols-2 gap-6 text-sm">
          <div class="space-y-2">
            <h4 class="font-semibold">Do</h4>
            <ul class="list-disc list-inside space-y-1 text-muted-foreground">
              <li>Use animations to provide feedback</li>
              <li>Keep animations subtle and fast (&lt; 300ms)</li>
              <li>Respect prefers-reduced-motion</li>
              <li>Use animations to guide attention</li>
            </ul>
          </div>
          
          <div class="space-y-2">
            <h4 class="font-semibold">Don't</h4>
            <ul class="list-disc list-inside space-y-1 text-muted-foreground">
              <li>Overuse animations for every interaction</li>
              <li>Use slow or jarring animations</li>
              <li>Animate large content blocks</li>
              <li>Distract from primary content</li>
            </ul>
          </div>
        </div>
      </Card.Content>
    </Card.Root>
  </section>
</div>