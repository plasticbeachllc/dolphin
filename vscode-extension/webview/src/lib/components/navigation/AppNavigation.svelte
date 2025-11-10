<script lang="ts">
  import * as NavigationMenu from "$lib/components/ui/navigation-menu";
  import { navigationMenuTriggerStyle } from "$lib/components/ui/navigation-menu/navigation-menu-trigger.svelte";
  import { Home, Workflow, Plug, Settings, User, MessageSquare } from "lucide-svelte";

  interface Props {
    currentPath?: string;
    onNavigate?: (path: string) => void;
    hasWorkspace?: boolean;
  }

  let { currentPath = "/", onNavigate, hasWorkspace = false }: Props = $props();

  function handleNavigation(path: string) {
    onNavigate?.(path);
  }
</script>

<div class="sticky top-0 z-50 w-full border-b bg-card backdrop-blur" role="navigation" aria-label="Main navigation">
  <div class="flex h-10 items-center justify-between px-3">
    <!-- Left side: Logo and main navigation -->
    <div class="flex items-center gap-2">
      <!-- Dolphin as Home Button -->
      <a
        href="/"
        class="inline-flex items-center justify-center rounded-md text-base font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground h-8 w-8 p-0"
        onclick={() => handleNavigation("/")}
        title="Home"
        aria-label="Home"
        aria-current={currentPath === "/" ? "page" : undefined}
      >
        🐬
      </a>

      <!-- Conversations Link - only show if workspace is open -->
      {#if hasWorkspace}
        <a
          href="/gallery/conversations"
          class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground h-8 px-3 gap-1.5"
          onclick={() => handleNavigation("/gallery/conversations")}
          title="Conversations"
          aria-label="Conversations"
          aria-current={currentPath === "/gallery/conversations" ? "page" : undefined}
        >
          <MessageSquare class="size-3.5" />
          <span class="text-xs">History</span>
        </a>
      {/if}

      <!-- Functions Dropdown -->
      <NavigationMenu.Root>
        <NavigationMenu.List class="flex items-center">
          <NavigationMenu.Item>
            <NavigationMenu.Trigger title="Functions" class="h-8 px-2">
              <Workflow class="size-3.5" />
              <span class="sr-only">Functions</span>
            </NavigationMenu.Trigger>
            <NavigationMenu.Content>
              <ul class="grid w-[200px] gap-1 p-2">
                <li>
                  <NavigationMenu.Link
                    href="/functions/code-review"
                    onclick={() => handleNavigation("/functions/code-review")}
                    class="block select-none space-y-0.5 rounded-md p-2 leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                  >
                    <div class="text-sm font-medium">Code Review</div>
                    <p class="text-xs text-muted-foreground">
                      AI-powered code review with analysis
                    </p>
                  </NavigationMenu.Link>
                </li>
                <li>
                  <NavigationMenu.Link
                    href="/functions/architect"
                    onclick={() => handleNavigation("/functions/architect")}
                    class="block select-none space-y-0.5 rounded-md p-2 leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                  >
                    <div class="text-sm font-medium">Architect</div>
                    <p class="text-xs text-muted-foreground">
                      Generate design specifications
                    </p>
                  </NavigationMenu.Link>
                </li>
              </ul>
            </NavigationMenu.Content>
          </NavigationMenu.Item>
        </NavigationMenu.List>
      </NavigationMenu.Root>

      <!-- MCP Providers Dropdown -->
      <NavigationMenu.Root>
        <NavigationMenu.List class="flex items-center">
          <NavigationMenu.Item>
            <NavigationMenu.Trigger title="MCP Providers" class="h-8 px-2">
              <Plug class="size-3.5" />
              <span class="sr-only">MCP Providers</span>
            </NavigationMenu.Trigger>
            <NavigationMenu.Content>
              <ul class="grid w-[180px] gap-1 p-2">
                <li>
                  <NavigationMenu.Link
                    href="#"
                    class="block select-none space-y-0.5 rounded-md p-2 leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground opacity-50 cursor-not-allowed"
                  >
                    <div class="text-sm font-medium leading-none">Coming soon</div>
                    <p class="line-clamp-2 text-xs leading-snug text-muted-foreground">
                      Provider management
                    </p>
                  </NavigationMenu.Link>
                </li>
              </ul>
            </NavigationMenu.Content>
          </NavigationMenu.Item>
        </NavigationMenu.List>
      </NavigationMenu.Root>
    </div>

    <!-- Right side: Settings and Profile -->
    <div class="flex items-center gap-1">
      <NavigationMenu.Root>
        <NavigationMenu.List class="flex items-center gap-1">
      <!-- Settings -->
      <NavigationMenu.Item>
        <NavigationMenu.Link>
          {#snippet child()}
            <a
              href="/settings"
              class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground h-8 w-8 p-0"
              onclick={() => handleNavigation("/settings")}
              title="Settings"
              aria-label="Settings"
              aria-current={currentPath === "/settings" ? "page" : undefined}
            >
              <Settings class="size-3.5" aria-hidden="true" />
            </a>
          {/snippet}
        </NavigationMenu.Link>
      </NavigationMenu.Item>

      <!-- User Profile -->
      <NavigationMenu.Item>
        <NavigationMenu.Link>
          {#snippet child()}
            <a
              href="/profile"
              class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground h-8 w-8 p-0"
              onclick={() => handleNavigation("/profile")}
              title="Profile"
              aria-label="Profile"
              aria-current={currentPath === "/profile" ? "page" : undefined}
            >
              <User class="size-3.5" aria-hidden="true" />
            </a>
          {/snippet}
        </NavigationMenu.Link>
      </NavigationMenu.Item>
        </NavigationMenu.List>
      </NavigationMenu.Root>
    </div>
  </div>
</div>
