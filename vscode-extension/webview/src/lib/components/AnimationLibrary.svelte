<script lang="ts">
  import { onMount } from 'svelte';
  import { Badge } from "$lib/components/ui/badge";

  /**
   * AnimationLibrary - Reusable animation components for Dolphin UI
   *
   * This component provides a collection of animation patterns that can be
   * used throughout the application to create delightful, consistent interactions.
   */

  // =============================================================================
  // StreamingText - Character-by-character reveal animation
  // =============================================================================

  interface StreamingTextProps {
    text: string;
    speed?: number;
    class?: string;
  }

  export function createStreamingText() {
    return {
      StreamingText: (node: HTMLElement, params: { text: string; speed?: number }) => {
        const speed = params.speed || 30;
        let currentIndex = 0;
        let interval: ReturnType<typeof setInterval>;

        const animate = () => {
          if (currentIndex < params.text.length) {
            node.textContent = params.text.slice(0, currentIndex + 1);
            currentIndex++;
          } else {
            clearInterval(interval);
          }
        };

        interval = setInterval(animate, speed);

        return {
          destroy() {
            clearInterval(interval);
          },
          update(newParams: { text: string; speed?: number }) {
            clearInterval(interval);
            currentIndex = 0;
            interval = setInterval(animate, newParams.speed || speed);
          }
        };
      }
    };
  }

  // =============================================================================
  // ProgressiveReveal - Staggered child animations
  // =============================================================================

  interface ProgressiveRevealProps {
    delay?: number;
    duration?: number;
    class?: string;
  }

  export function createProgressiveReveal() {
    return {
      ProgressiveReveal: (node: HTMLElement, params: ProgressiveRevealProps = {}) => {
        const delay = params.delay || 50;
        const duration = params.duration || 300;

        const children = Array.from(node.children) as HTMLElement[];

        children.forEach((child, index) => {
          child.style.opacity = '0';
          child.style.transform = 'translateY(12px)';
          child.style.transition = `opacity ${duration}ms ease-out, transform ${duration}ms ease-out`;

          setTimeout(() => {
            child.style.opacity = '1';
            child.style.transform = 'translateY(0)';
          }, index * delay);
        });

        return {
          destroy() {
            children.forEach(child => {
              child.style.opacity = '';
              child.style.transform = '';
              child.style.transition = '';
            });
          }
        };
      }
    };
  }

  // =============================================================================
  // CounterAnimation - Smooth number transitions
  // =============================================================================

  interface CounterAnimationProps {
    from: number;
    to: number;
    duration?: number;
    format?: (value: number) => string;
  }

  export function createCounterAnimation() {
    return {
      CounterAnimation: (node: HTMLElement, params: CounterAnimationProps) => {
        const duration = params.duration || 1000;
        const format = params.format || ((v: number) => Math.round(v).toString());
        const startTime = Date.now();
        const difference = params.to - params.from;

        const animate = () => {
          const elapsed = Date.now() - startTime;
          const progress = Math.min(elapsed / duration, 1);

          // Easing function (ease-out cubic)
          const eased = 1 - Math.pow(1 - progress, 3);
          const current = params.from + (difference * eased);

          node.textContent = format(current);

          if (progress < 1) {
            requestAnimationFrame(animate);
          }
        };

        requestAnimationFrame(animate);

        return {
          destroy() {
            // Cleanup handled automatically
          },
          update(newParams: CounterAnimationProps) {
            // Re-initialize with new params
            const newDuration = newParams.duration || duration;
            const newFormat = newParams.format || format;
            const newStartTime = Date.now();
            const newDifference = newParams.to - newParams.from;

            const newAnimate = () => {
              const elapsed = Date.now() - newStartTime;
              const progress = Math.min(elapsed / newDuration, 1);
              const eased = 1 - Math.pow(1 - progress, 3);
              const current = newParams.from + (newDifference * eased);

              node.textContent = newFormat(current);

              if (progress < 1) {
                requestAnimationFrame(newAnimate);
              }
            };

            requestAnimationFrame(newAnimate);
          }
        };
      }
    };
  }
</script>

<!-- =============================================================================
     Component Snippets - Ready-to-use animation patterns
     ============================================================================= -->

{#snippet PulseIndicator(props?: { children?: any; class?: string })}
  <Badge variant="secondary" class="flex items-center gap-2 {props?.class || ''}">
    <span class="flex gap-1">
      <span class="size-1 rounded-full bg-current animate-pulse"></span>
      <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 150ms" ></span>
      <span class="size-1 rounded-full bg-current animate-pulse" style="animation-delay: 300ms" ></span>
    </span>
    {#if props?.children}
      {@render props.children()}
    {/if}
  </Badge>
{/snippet}

{#snippet ThinkingDots(props?: { class?: string })}
  <div class="flex gap-1 {props?.class || ''}">
    <span class="size-1.5 rounded-full bg-current animate-typing-dot"></span>
    <span class="size-1.5 rounded-full bg-current animate-typing-dot" style="animation-delay: 0.2s" ></span>
    <span class="size-1.5 rounded-full bg-current animate-typing-dot" style="animation-delay: 0.4s" ></span>
  </div>
{/snippet}

{#snippet BreathingBadge(props: { children: any; class?: string })}
  <Badge variant="outline" class="animate-breathe {props?.class || ''}">
    {@render props.children()}
  </Badge>
{/snippet}

{#snippet GlowingStatus(props: { active?: boolean; class?: string })}
  <span
    class="relative inline-flex size-2 rounded-full {props?.class || ''}"
    class:animate-pulse-glow={props?.active}
  >
    <span
      class="absolute inline-flex h-full w-full rounded-full opacity-75"
      class:bg-green-400={props?.active}
      class:bg-muted-foreground={!props?.active}
    ></span>
    <span
      class="relative inline-flex size-2 rounded-full"
      class:bg-green-500={props?.active}
      class:bg-muted-foreground={!props?.active}
    ></span>
  </span>
{/snippet}

{#snippet ShimmerLoader(props: { class?: string; height?: string; width?: string })}
  <div
    class="rounded-md animate-shimmer {props?.class || ''}"
    style:height={props?.height || '100%'}
    style:width={props?.width || '100%'}
  ></div>
{/snippet}

{#snippet SlideInCard(props: { children: any; delay?: number; class?: string })}
  <div
    class="animate-slide-in-up {props?.class || ''}"
    style:animation-delay={props?.delay ? `${props.delay}ms` : '0ms'}
  >
    {@render props.children()}
  </div>
{/snippet}

{#snippet FadeIn(props: { children: any; delay?: number; class?: string })}
  <div
    class="animate-fade-in {props?.class || ''}"
    style:animation-delay={props?.delay ? `${props.delay}ms` : '0ms'}
  >
    {@render props.children()}
  </div>
{/snippet}

{#snippet BounceSubtle(props: { children: any; class?: string })}
  <div class="animate-bounce-subtle {props?.class || ''}">
    {@render props.children()}
  </div>
{/snippet}

{#snippet SpinnerDots(props?: { class?: string; size?: 'sm' | 'md' | 'lg' })}
  {@const sizeClass = props?.size === 'sm' ? 'size-1' : props?.size === 'lg' ? 'size-2' : 'size-1.5'}
  <div class="flex items-center gap-1 {props?.class || ''}">
    <span class="{sizeClass} rounded-full bg-current animate-pulse" ></span>
    <span class="{sizeClass} rounded-full bg-current animate-pulse" style="animation-delay: 150ms" ></span>
    <span class="{sizeClass} rounded-full bg-current animate-pulse" style="animation-delay: 300ms" ></span>
  </div>
{/snippet}

{#snippet ProgressBar(props: { value?: number; indeterminate?: boolean; class?: string })}
  <div class="relative h-1 w-full overflow-hidden rounded-full bg-secondary {props?.class || ''}">
    {#if props?.indeterminate}
      <div
        class="absolute h-full w-1/3 bg-primary animate-shimmer"
        style="animation-duration: 1.5s"
      ></div>
    {:else}
      <div
        class="h-full bg-primary transition-all duration-300 ease-out"
        style:width="{props?.value || 0}%"
      ></div>
    {/if}
  </div>
{/snippet}

{#snippet PulseRing(props: { children: any; active?: boolean; class?: string })}
  <div class="relative inline-flex {props?.class || ''}">
    {@render props.children()}
    {#if props?.active}
      <span class="absolute inset-0 rounded-full animate-ping opacity-75 bg-primary -z-10"></span>
    {/if}
  </div>
{/snippet}

{#snippet TypewriterText(props: { text: string; speed?: number; class?: string })}
  {@const { StreamingText } = createStreamingText()}
  <span
    class="{props?.class || ''}"
    use:StreamingText={{ text: props.text, speed: props?.speed }}
  ></span>
{/snippet}

{#snippet StaggeredList(props: { children: any; delay?: number; class?: string })}
  {@const { ProgressiveReveal } = createProgressiveReveal()}
  <div
    class="{props?.class || ''}"
    use:ProgressiveReveal={{ delay: props?.delay }}
  >
    {@render props.children()}
  </div>
{/snippet}

{#snippet AnimatedCounter(props: { from: number; to: number; duration?: number; format?: (v: number) => string; class?: string })}
  {@const { CounterAnimation } = createCounterAnimation()}
  <span
    class="{props?.class || ''}"
    use:CounterAnimation={{
      from: props.from,
      to: props.to,
      duration: props?.duration,
      format: props?.format
    }}
  ></span>
{/snippet}

<!--
  Usage Examples:

  1. Thinking indicator:
     {@render ThinkingDots()}

  2. Pulsing status badge:
     {@render PulseIndicator()}
       Thinking...
     {/render}

  3. Glowing status dot:
     {@render GlowingStatus({ active: true })}

  4. Shimmer loader:
     {@render ShimmerLoader({ height: '100px', width: '100%' })}

  5. Slide-in animation:
     {@render SlideInCard({ delay: 100 })}
       <Card.Root>Content</Card.Root>
     {/render}

  6. Animated counter:
     {@render AnimatedCounter({
       from: 0,
       to: 100,
       format: (v) => `${Math.round(v)}%`
     })}

  7. Staggered list reveal:
     {@render StaggeredList({ delay: 50 })}
       <div>Item 1</div>
       <div>Item 2</div>
       <div>Item 3</div>
     {/render}
-->