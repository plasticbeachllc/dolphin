<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import * as Separator from "$lib/components/ui/separator";

  /**
   * LoadingStates - Gallery of loading state patterns for Dolphin UI
   *
   * This component provides examples of skeleton loaders and loading patterns
   * for different UI elements.
   */
</script>

<div class="space-y-8 p-6">
  <div class="space-y-2">
    <h2 class="text-2xl font-bold">Loading States Gallery</h2>
    <p class="text-sm text-muted-foreground">
      Consistent loading patterns for different UI components
    </p>
  </div>

  <Separator.Root />

  <!-- Card Loading Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Card Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading message cards, tool results, etc.</p>
    </div>

    <Card.Root>
      <Card.Header>
        <Skeleton class="h-4 w-[250px]" />
        <Skeleton class="h-4 w-[200px]" />
      </Card.Header>
      <Card.Content>
        <Skeleton class="h-[125px] w-full" />
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Text Content Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Text Content Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading paragraph content</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="space-y-2">
          <Skeleton class="h-4 w-full" />
          <Skeleton class="h-4 w-full" />
          <Skeleton class="h-4 w-[80%]" />
          <Skeleton class="h-4 w-[60%]" />
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Timeline Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Timeline Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading plan timelines</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="flex gap-4">
          {#each Array(5) as _, i}
            <Skeleton class="size-10 rounded-full" />
          {/each}
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Tool Card Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Tool Card Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading tool execution results</p>
    </div>

    <Card.Root>
      <Card.Header class="pb-3">
        <div class="flex items-center justify-between">
          <Skeleton class="h-6 w-[150px]" />
          <Skeleton class="h-4 w-[60px]" />
        </div>
      </Card.Header>
      <Card.Content class="space-y-2">
        <Skeleton class="h-4 w-full" />
        <Skeleton class="h-20 w-full" />
        <Skeleton class="h-4 w-[100px]" />
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- List Item Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">List Item Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading lists of items</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="space-y-4">
          {#each Array(3) as _, i}
            <div class="flex items-center gap-4">
              <Skeleton class="size-12 rounded-md" />
              <div class="space-y-2 flex-1">
                <Skeleton class="h-4 w-full" />
                <Skeleton class="h-3 w-[70%]" />
              </div>
            </div>
          {/each}
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Avatar + Text Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Avatar + Text Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading user/assistant headers</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="flex items-center gap-4">
          <Skeleton class="size-10 rounded-full" />
          <div class="space-y-2 flex-1">
            <Skeleton class="h-4 w-[200px]" />
            <Skeleton class="h-3 w-[150px]" />
          </div>
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Table Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Table Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading tabular data</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="space-y-3">
          <!-- Header -->
          <div class="flex gap-4 pb-2 border-b border-border">
            <Skeleton class="h-4 w-[120px]" />
            <Skeleton class="h-4 w-[150px]" />
            <Skeleton class="h-4 w-[100px]" />
          </div>
          <!-- Rows -->
          {#each Array(4) as _, i}
            <div class="flex gap-4">
              <Skeleton class="h-4 w-[120px]" />
              <Skeleton class="h-4 w-[150px]" />
              <Skeleton class="h-4 w-[100px]" />
            </div>
          {/each}
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Code Block Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Code Block Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading code snippets</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="space-y-2 bg-secondary/50 p-4 rounded-md font-mono">
          <Skeleton class="h-3 w-[40%]" />
          <Skeleton class="h-3 w-[60%]" />
          <Skeleton class="h-3 w-[50%]" />
          <Skeleton class="h-3 w-[70%]" />
          <Skeleton class="h-3 w-[45%]" />
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Stats/Metrics Skeleton -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Stats/Metrics Skeleton</h3>
      <p class="text-sm text-muted-foreground">Used for loading dashboard metrics</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      {#each Array(3) as _, i}
        <Card.Root>
          <Card.Header class="pb-2">
            <Skeleton class="h-4 w-[100px]" />
          </Card.Header>
          <Card.Content>
            <Skeleton class="h-8 w-[80px] mb-2" />
            <Skeleton class="h-3 w-[120px]" />
          </Card.Content>
        </Card.Root>
      {/each}
    </div>
  </section>

  <Separator.Root />

  <!-- Shimmer Animation -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Shimmer Animation</h3>
      <p class="text-sm text-muted-foreground">Used for large content areas or images</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="h-48 w-full rounded-md animate-shimmer"></div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Inline Loading Badges -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Inline Loading Indicators</h3>
      <p class="text-sm text-muted-foreground">Used for inline status updates</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="space-y-4">
          <!-- Pulsing dots -->
          <div class="flex items-center gap-2">
            <Badge variant="secondary" class="flex items-center gap-2">
              <span>Processing</span>
              <div class="flex gap-0.5">
                <span class="size-1 rounded-full bg-current animate-pulse"></span>
                <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 150ms" ></span>
                <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 300ms" ></span>
              </div>
            </Badge>
            <span class="text-sm text-muted-foreground">Pulsing dots</span>
          </div>

          <!-- Typing animation -->
          <div class="flex items-center gap-2">
            <Badge variant="secondary" class="flex items-center gap-2">
              <span>Thinking</span>
              <div class="flex gap-1">
                <span class="size-1.5 rounded-full bg-current animate-typing-dot"></span>
                <span class="size-1.5 rounded-full bg-current animate-typing-dot" style="animation-delay: 0.2s" ></span>
                <span class="size-1.5 rounded-full bg-current animate-typing-dot" style="animation-delay: 0.4s" ></span>
              </div>
            </Badge>
            <span class="text-sm text-muted-foreground">Typing dots</span>
          </div>

          <!-- Breathing badge -->
          <div class="flex items-center gap-2">
            <Badge variant="outline" class="animate-breathe">
              Connecting
            </Badge>
            <span class="text-sm text-muted-foreground">Breathing animation</span>
          </div>

          <!-- Spinner -->
          <div class="flex items-center gap-2">
            <Badge variant="secondary" class="flex items-center gap-2">
              <div class="size-3 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
              <span>Loading</span>
            </Badge>
            <span class="text-sm text-muted-foreground">Spinner</span>
          </div>

          <!-- Pulse glow -->
          <div class="flex items-center gap-2">
            <Badge variant="default" class="animate-pulse-glow">
              Active
            </Badge>
            <span class="text-sm text-muted-foreground">Pulse glow</span>
          </div>
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Progress Bars -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Progress Bars</h3>
      <p class="text-sm text-muted-foreground">Used for determinate and indeterminate progress</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6 space-y-6">
        <!-- Determinate progress -->
        <div class="space-y-2">
          <div class="flex items-center justify-between text-sm">
            <span class="text-muted-foreground">Determinate progress</span>
            <span class="font-medium">45%</span>
          </div>
          <div class="h-2 w-full overflow-hidden rounded-full bg-secondary">
            <div class="h-full bg-primary transition-all duration-300 ease-out" style="width: 45%"></div>
          </div>
        </div>

        <!-- Indeterminate progress -->
        <div class="space-y-2">
          <span class="text-sm text-muted-foreground">Indeterminate progress</span>
          <div class="relative h-2 w-full overflow-hidden rounded-full bg-secondary">
            <div
              class="absolute h-full w-1/3 bg-primary animate-shimmer"
              style="animation-duration: 1.5s"
            ></div>
          </div>
        </div>

        <!-- Thin progress bar -->
        <div class="space-y-2">
          <span class="text-sm text-muted-foreground">Thin progress bar</span>
          <div class="h-1 w-full overflow-hidden rounded-full bg-secondary">
            <div class="h-full bg-primary transition-all duration-300 ease-out" style="width: 70%"></div>
          </div>
        </div>
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Composite Loading States -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Composite Loading Patterns</h3>
      <p class="text-sm text-muted-foreground">Real-world combinations</p>
    </div>

    <!-- Message loading -->
    <Card.Root>
      <Card.Header class="flex flex-row items-center gap-2 pb-2">
        <Skeleton class="size-8 rounded-full" />
        <div class="flex-1 space-y-2">
          <Skeleton class="h-4 w-[100px]" />
          <Skeleton class="h-3 w-[80px]" />
        </div>
      </Card.Header>
      <Card.Content class="space-y-2">
        <Skeleton class="h-4 w-full" />
        <Skeleton class="h-4 w-[90%]" />
        <Skeleton class="h-4 w-[70%]" />
      </Card.Content>
    </Card.Root>

    <!-- Tool execution loading -->
    <Card.Root>
      <Card.Header class="pb-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Badge variant="secondary" class="flex items-center gap-2">
              <div class="size-3 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
              <span>search</span>
            </Badge>
          </div>
          <Skeleton class="h-4 w-[60px]" />
        </div>
      </Card.Header>
      <Card.Content class="space-y-3">
        <div class="text-sm text-muted-foreground flex items-center gap-2">
          <div class="flex gap-1">
            <span class="size-1 rounded-full bg-current animate-pulse"></span>
            <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 150ms" ></span>
            <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 300ms" ></span>
          </div>
          Searching knowledge base...
        </div>
        <Skeleton class="h-20 w-full" />
      </Card.Content>
    </Card.Root>
  </section>

  <Separator.Root />

  <!-- Usage Guidelines -->
  <section class="space-y-4">
    <div>
      <h3 class="text-lg font-semibold">Usage Guidelines</h3>
      <p class="text-sm text-muted-foreground">Best practices for loading states</p>
    </div>

    <Card.Root>
      <Card.Content class="pt-6">
        <div class="space-y-4 text-sm">
          <div>
            <h4 class="font-semibold mb-2">When to use Skeleton loaders:</h4>
            <ul class="list-disc list-inside space-y-1 text-muted-foreground">
              <li>Content structure is known (cards, lists, tables)</li>
              <li>Loading time is predictable (&lt; 3 seconds)</li>
              <li>Preserves layout stability</li>
            </ul>
          </div>

          <div>
            <h4 class="font-semibold mb-2">When to use Spinners/Dots:</h4>
            <ul class="list-disc list-inside space-y-1 text-muted-foreground">
              <li>Content structure is unknown</li>
              <li>Quick operations (&lt; 1 second)</li>
              <li>Inline status indicators</li>
            </ul>
          </div>

          <div>
            <h4 class="font-semibold mb-2">When to use Progress bars:</h4>
            <ul class="list-disc list-inside space-y-1 text-muted-foreground">
              <li>Progress can be measured (determinate)</li>
              <li>Long-running operations (&gt; 5 seconds)</li>
              <li>File uploads, downloads, processing</li>
            </ul>
          </div>

          <div>
            <h4 class="font-semibold mb-2">Animation timing:</h4>
            <ul class="list-disc list-inside space-y-1 text-muted-foreground">
              <li>Skeleton: No animation or subtle shimmer</li>
              <li>Dots/Spinner: 1-2 second loop</li>
              <li>Progress: Smooth 300ms transitions</li>
            </ul>
          </div>
        </div>
      </Card.Content>
    </Card.Root>
  </section>
</div>

<style>
  /* Additional styles for shimmer animation customization */
  .animate-shimmer {
    background: linear-gradient(
      90deg,
      hsl(var(--muted)) 0%,
      hsl(var(--accent)) 50%,
      hsl(var(--muted)) 100%
    );
    background-size: 200% 100%;
  }
</style>
