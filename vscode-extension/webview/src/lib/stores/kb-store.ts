// vscode-extension/webview/src/lib/stores/kb-store.ts
import { writable, derived } from 'svelte/store';

export interface KBStats {
  filesCount: number;
  chunksCount: number;
  totalTokens: number;
  lastUpdated: string;
  embedModel: string;
}

export interface KBProgress {
  current: number;
  total: number;
  currentFile: string;
  indexed: number;
  skipped: number;
}

export type KBStatus = 'offline' | 'ready' | 'indexing' | 'reindexing' | 'stale' | 'error';

export interface KBState {
  initialized: boolean;
  repoName: string | null;
  status: KBStatus;
  stats: KBStats;
  progress?: KBProgress;
  error?: string;
}

const defaultState: KBState = {
  initialized: false,
  repoName: null,
  status: 'offline',
  stats: {
    filesCount: 0,
    chunksCount: 0,
    totalTokens: 0,
    lastUpdated: 'Never',
    embedModel: 'large'
  }
};

// Main KB store
export const kbStore = writable<KBState>(defaultState);

// Derived stores for specific UI needs
export const isIndexing = derived(
  kbStore,
  $kb => $kb.status === 'indexing' || $kb.status === 'reindexing'
);

export const canReindex = derived(
  kbStore,
  $kb => $kb.initialized && ($kb.status === 'ready' || $kb.status === 'stale')
);

export const needsReindex = derived(
  kbStore,
  $kb => $kb.status === 'stale' || ($kb.initialized && $kb.stats.chunksCount === 0)
);

// Actions
export const kbActions = {
  /**
   * Initialize KB state with repository info
   */
  initialize(repoName: string, stats: Partial<KBStats>) {
    kbStore.update(state => ({
      ...state,
      initialized: true,
      repoName,
      status: 'ready',
      stats: { ...state.stats, ...stats }
    }));
  },

  /**
   * Update KB status
   */
  setStatus(status: KBStatus, error?: string) {
    kbStore.update(state => ({
      ...state,
      status,
      error
    }));
  },

  /**
   * Update statistics
   */
  updateStats(stats: Partial<KBStats>) {
    kbStore.update(state => ({
      ...state,
      stats: { ...state.stats, ...stats }
    }));
  },

  /**
   * Update indexing progress
   */
  updateProgress(progress: Partial<KBProgress>) {
    kbStore.update(state => {
      const newProgress = state.progress
        ? { ...state.progress, ...progress }
        : { current: 0, total: 0, currentFile: '', indexed: 0, skipped: 0, ...progress };
      console.log('[kbStore] updateProgress called with:', progress, '-> resulting in:', newProgress);
      return {
        ...state,
        progress: newProgress
      };
    });
  },

  /**
   * Clear indexing progress
   */
  clearProgress() {
    kbStore.update(state => ({
      ...state,
      progress: undefined
    }));
  },

  /**
   * Mark KB as stale (needs reindex)
   */
  markStale() {
    kbStore.update(state => ({
      ...state,
      status: 'stale'
    }));
  },

  /**
   * Reset KB state
   */
  reset() {
    kbStore.set(defaultState);
  }
};

// Cost estimation utilities
export interface CostEstimate {
  tokens: number;
  costUSD: string;
  estimatedTime: string;
}

export function estimateReindexCost(stats: KBStats): CostEstimate {
  // Using Voyage AI pricing (example)
  const COST_PER_MILLION_TOKENS = 0.12; // $0.12 per 1M tokens for large model
  
  const estimatedTokens = stats.totalTokens;
  const costUSD = (estimatedTokens / 1_000_000) * COST_PER_MILLION_TOKENS;
  
  // Estimate time (rough calculation: ~10 chunks per second)
  const CHUNKS_PER_SECOND = 10;
  const estimatedSeconds = Math.ceil(stats.chunksCount / CHUNKS_PER_SECOND);
  
  return {
    tokens: estimatedTokens,
    costUSD: costUSD.toFixed(2),
    estimatedTime: formatDuration(estimatedSeconds)
  };
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  
  if (minutes < 60) {
    return remainingSeconds > 0 
      ? `${minutes}m ${remainingSeconds}s`
      : `${minutes}m`;
  }
  
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  
  return remainingMinutes > 0
    ? `${hours}h ${remainingMinutes}m`
    : `${hours}h`;
}