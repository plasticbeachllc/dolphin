<script lang="ts">
  import { onMount } from 'svelte';
  
  interface PlanStep {
    id: string;
    description: string;
    status: 'pending' | 'running' | 'completed' | 'error';
  }
  
  interface Props {
    steps: PlanStep[];
  }
  
  let { steps }: Props = $props();
  
  let scrollContainer: HTMLDivElement;
  let isDragging = $state(false);
  let startX = $state(0);
  let scrollLeft = $state(0);
  
  function handleMouseDown(e: MouseEvent) {
    isDragging = true;
    startX = e.pageX - scrollContainer.offsetLeft;
    scrollLeft = scrollContainer.scrollLeft;
  }
  
  function handleMouseMove(e: MouseEvent) {
    if (!isDragging) return;
    e.preventDefault();
    const x = e.pageX - scrollContainer.offsetLeft;
    scrollContainer.scrollLeft = scrollLeft - (x - startX) * 2;
  }
  
  function handleMouseUp() {
    isDragging = false;
  }
  
  const statusColors = {
    pending: 'bg-gray-400',
    running: 'bg-blue-500',
    completed: 'bg-green-500',
    error: 'bg-red-500'
  };
</script>

<div class="plan-timeline">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    bind:this={scrollContainer}
    class="timeline-scroll"
    class:dragging={isDragging}
    onmousedown={handleMouseDown}
    onmouseup={handleMouseUp}
    onmouseleave={handleMouseUp}
    onmousemove={handleMouseMove}
  >
    <div class="timeline-track">
      {#each steps as step, i (step.id)}
        <div class="timeline-step">
          {#if i > 0}
            <div class="connector" class:completed={steps[i-1].status === 'completed'}></div>
          {/if}
          
          <div 
            class="step-circle {statusColors[step.status]}"
            class:pulsing={step.status === 'running'}
          >
            {i + 1}
          </div>
          
          <div class="step-label">{step.description}</div>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .plan-timeline {
    overflow: hidden;
    padding: 1rem 0;
    background: hsl(var(--secondary));
    border-radius: 3px;
  }
  
  .timeline-scroll {
    overflow-x: auto;
    cursor: grab;
  }
  
  .timeline-scroll.dragging {
    cursor: grabbing;
    user-select: none;
  }
  
  .timeline-track {
    display: flex;
    padding: 0 1rem;
    min-width: min-content;
  }
  
  .timeline-step {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 120px;
  }
  
  .connector {
    position: absolute;
    top: 20px;
    right: 50%;
    width: 100%;
    height: 2px;
    background: hsl(var(--border));
  }
  
  .connector.completed {
    background: #10b981;
  }
  
  .step-circle {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 600;
    z-index: 1;
  }
  
  .step-circle.pulsing {
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }
  
  .step-label {
    margin-top: 0.5rem;
    text-align: center;
    font-size: 0.75rem;
    max-width: 100px;
  }
</style>