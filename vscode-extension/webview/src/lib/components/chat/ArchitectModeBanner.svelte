<script lang="ts">
  import { Building2, Sparkles } from "lucide-svelte";
</script>

<div class="architect-banner">
  <div class="banner-content">
    <div class="icon-wrapper">
      <Building2 class="h-5 w-5" />
      <Sparkles class="h-3 w-3 sparkle" />
    </div>
    <div class="text-content">
      <strong>Architect Mode Active</strong>
      <span class="description">Systematic codebase discovery enabled</span>
    </div>
  </div>
</div>

<style>
  .architect-banner {
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.15) 0%, rgba(118, 75, 162, 0.15) 100%);
    border: 1px solid rgba(102, 126, 234, 0.3);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 16px;
    backdrop-filter: blur(10px);
  }

  .banner-content {
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--vscode-foreground);
  }

  .icon-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  :global(.sparkle) {
    position: absolute;
    top: -2px;
    right: -2px;
    color: rgba(102, 126, 234, 0.8);
    animation: sparkle 2s ease-in-out infinite;
  }

  @keyframes sparkle {
    0%, 100% {
      opacity: 0.5;
      transform: scale(0.8);
    }
    50% {
      opacity: 1;
      transform: scale(1.1);
    }
  }

  .text-content {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .text-content strong {
    font-size: 14px;
    font-weight: 600;
    color: rgba(102, 126, 234, 1);
  }

  .description {
    font-size: 12px;
    opacity: 0.8;
  }
</style>
