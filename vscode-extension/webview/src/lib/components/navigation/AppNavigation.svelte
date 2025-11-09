<script lang="ts">
  import * as NavigationMenu from "$lib/components/ui/navigation-menu";
  import { navigationMenuTriggerStyle } from "$lib/components/ui/navigation-menu/navigation-menu-trigger.svelte";
  import { Home, Workflow, Plug, Settings, User } from "lucide-svelte";

  interface Props {
    currentPath?: string;
    onNavigate?: (path: string) => void;
  }

  let { currentPath = "/", onNavigate }: Props = $props();

  function handleNavigation(path: string) {
    onNavigate?.(path);
  }
</script>

<div class="sticky top-0 z-50 w-full border-b bg-card backdrop-blur">
  <div class="flex h-14 items-center justify-between px-4">
    <!-- Left side: Logo and main navigation -->
    <div class="flex items-center gap-4">
      <div class="flex items-center gap-2">
        <span class="text-lg font-semibold">🐬 Dolphin</span>
      </div>
      
      <!-- Home -->
      <NavigationMenu.Root>
        <NavigationMenu.List class="flex items-center">
          <NavigationMenu.Item>
            <NavigationMenu.Link>
              {#snippet child()}
                <a
                  href="/"
                  class={navigationMenuTriggerStyle()}
                  onclick={() => handleNavigation("/")}
                >
                  <Home class="size-4 mr-2" />
                  Home
                </a>
              {/snippet}
            </NavigationMenu.Link>
          </NavigationMenu.Item>
        </NavigationMenu.List>
      </NavigationMenu.Root>

      <!-- Functions Dropdown -->
      <NavigationMenu.Root>
        <NavigationMenu.List class="flex items-center">
          <NavigationMenu.Item>
            <NavigationMenu.Trigger>
              <Workflow class="size-4 mr-2" />
              Functions
            </NavigationMenu.Trigger>
            <NavigationMenu.Content>
              <ul class="grid w-[500px] gap-3 p-4">
                <li>
                  <NavigationMenu.Link
                    href="/functions/code-review"
                    onclick={() => handleNavigation("/functions/code-review")}
                    class="block select-none space-y-1 rounded-md p-3 leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                  >
                    <div class="font-medium">Code Review</div>
                    <p class="text-sm text-muted-foreground">
                      AI-powered code review with goal-oriented analysis
                    </p>
                  </NavigationMenu.Link>
                </li>
                <li>
                  <NavigationMenu.Link
                    href="/functions/architect"
                    onclick={() => handleNavigation("/functions/architect")}
                    class="block select-none space-y-1 rounded-md p-3 leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                  >
                    <div class="font-medium">Architect</div>
                    <p class="text-sm text-muted-foreground">
                      Generate architectural plans and design specifications
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
            <NavigationMenu.Trigger>
              <Plug class="size-4 mr-2" />
              MCP Providers
            </NavigationMenu.Trigger>
            <NavigationMenu.Content>
              <ul class="grid w-[200px] gap-1 p-2">
                <li>
                  <NavigationMenu.Link
                    href="#"
                    class="block select-none space-y-1 rounded-md p-3 leading-none no-underline outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground opacity-50 cursor-not-allowed"
                  >
                    <div class="text-sm font-medium leading-none">Coming soon</div>
                    <p class="line-clamp-2 text-sm leading-snug text-muted-foreground">
                      MCP provider management
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
    <div class="flex items-center gap-2">
      <NavigationMenu.Root>
        <NavigationMenu.List class="flex items-center gap-2">
      <!-- Settings -->
      <NavigationMenu.Item>
        <NavigationMenu.Link>
          {#snippet child()}
            <a
              href="/settings"
              class={navigationMenuTriggerStyle()}
              onclick={() => handleNavigation("/settings")}
            >
              <Settings class="size-4 mr-2" />
              Settings
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
              class={navigationMenuTriggerStyle()}
              onclick={() => handleNavigation("/profile")}
            >
              <User class="size-4 mr-2" />
              Profile
            </a>
          {/snippet}
        </NavigationMenu.Link>
      </NavigationMenu.Item>
        </NavigationMenu.List>
      </NavigationMenu.Root>
    </div>
  </div>
</div>