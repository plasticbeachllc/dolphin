<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import { Button } from "$lib/components/ui/button";
  import { Building2, Sparkles } from "lucide-svelte";
</script>

<div class="flex h-full flex-col items-center justify-center p-8">
  <Card.Root class="w-full max-w-2xl">
    <Card.Header>
      <div class="flex items-center gap-3">
        <div class="rounded-lg bg-primary/10 p-3">
          <Building2 class="size-6 text-primary" />
        </div>
        <div>
          <Card.Title>Architect</Card.Title>
          <Card.Description>
            Generate architectural plans and design specifications
          </Card.Description>
        </div>
      </div>
    </Card.Header>
    <Card.Content class="space-y-4">
      <div class="rounded-lg border border-dashed p-8 text-center">
        <Sparkles class="mx-auto mb-4 size-12 text-muted-foreground/50" />
        <h3 class="mb-2 text-lg font-semibold">Coming Soon</h3>
        <p class="text-sm text-muted-foreground">
          This feature is currently under development. Soon you'll be able to:
        </p>
      </div>

      <div class="space-y-3">
        <div class="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <div class="mt-0.5 size-2 rounded-full bg-primary"></div>
          <div class="flex-1">
            <p class="text-sm font-medium">Define Project Requirements</p>
            <p class="text-xs text-muted-foreground">
              Describe your project goals and technical constraints
            </p>
          </div>
        </div>

        <div class="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <div class="mt-0.5 size-2 rounded-full bg-primary"></div>
          <div class="flex-1">
            <p class="text-sm font-medium">Generate Architecture Plan</p>
            <p class="text-xs text-muted-foreground">
              AI creates a comprehensive architectural design document
            </p>
          </div>
        </div>

        <div class="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <div class="mt-0.5 size-2 rounded-full bg-primary"></div>
          <div class="flex-1">
            <p class="text-sm font-medium">Review and Refine</p>
            <p class="text-xs text-muted-foreground">
              Iterate on the design with AI assistance before implementation
            </p>
          </div>
        </div>
      </div>
    </Card.Content>
    <Card.Footer>
      <Button variant="outline" class="w-full" disabled>
        Create Architecture Plan
      </Button>
    </Card.Footer>
  </Card.Root>
</div>