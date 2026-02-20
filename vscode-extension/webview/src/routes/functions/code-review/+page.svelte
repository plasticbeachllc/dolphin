<script lang="ts">
  import * as Card from "$lib/components/ui/card";
  import { Button } from "$lib/components/ui/button";
  import { FileSearch, Sparkles } from "lucide-svelte";
</script>

<div class="flex h-full flex-col items-center justify-center p-8">
  <Card.Root class="w-full max-w-2xl">
    <Card.Header>
      <div class="flex items-center gap-3">
        <div class="rounded-lg bg-primary/10 p-3">
          <FileSearch class="size-6 text-primary" />
        </div>
        <div>
          <Card.Title>Code Review</Card.Title>
          <Card.Description>
            AI-powered code review with goal-oriented analysis
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
            <p class="text-sm font-medium">Define Review Goals</p>
            <p class="text-xs text-muted-foreground">
              Specify what you're trying to accomplish with the review
            </p>
          </div>
        </div>

        <div class="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <div class="mt-0.5 size-2 rounded-full bg-primary"></div>
          <div class="flex-1">
            <p class="text-sm font-medium">Select Target Files</p>
            <p class="text-xs text-muted-foreground">
              Choose files to review or use an LLM prompt to identify them
            </p>
          </div>
        </div>

        <div class="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
          <div class="mt-0.5 size-2 rounded-full bg-primary"></div>
          <div class="flex-1">
            <p class="text-sm font-medium">Get AI Analysis</p>
            <p class="text-xs text-muted-foreground">
              Receive detailed feedback and suggestions for improvement
            </p>
          </div>
        </div>
      </div>
    </Card.Content>
    <Card.Footer>
      <Button variant="outline" class="w-full" disabled>
        Start Code Review
      </Button>
    </Card.Footer>
  </Card.Root>
</div>