// vscode-extension/webview/src/lib/api/kb-api.ts
import { vscode } from './vscode';

export interface RepoStats {
  name: string;
  path: string;
  files_count: number;
  chunks_count: number;
  total_tokens: number;
  embed_model: string;
  last_indexed: string | null;
  needs_reindex: boolean;
}

export interface ReindexRequest {
  mode: 'full' | 'incremental';
  confirmed: boolean;
  clear_existing?: boolean;
}

export interface ReindexResponse {
  task_id: string;
  mode: string;
  message: string;
}

export interface IndexStatus {
  task_id: string;
  status: string;
  progress: number;
  total: number;
  indexed: number;
  skipped: number;
  error: string | null;
  result: any;
}

/**
 * KB API client for interacting with the Knowledge Base backend
 */
export const kbApi = {
  /**
   * Get repository statistics
   */
  async getRepoStats(repoName: string): Promise<RepoStats> {
    // Send request through VSCode API
    const response = await fetch(`http://127.0.0.1:7777/v1/repos/${repoName}/stats`);
    
    if (!response.ok) {
      throw new Error(`Failed to get repo stats: ${response.statusText}`);
    }
    
    return await response.json();
  },

  /**
   * Trigger a reindex operation
   */
  async triggerReindex(repoName: string, request: ReindexRequest): Promise<ReindexResponse> {
    const response = await fetch(`http://127.0.0.1:7777/v1/repos/${repoName}/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to trigger reindex: ${response.statusText}`);
    }
    
    return await response.json();
  },

  /**
   * Get indexing task status
   */
  async getIndexStatus(taskId: string): Promise<IndexStatus> {
    const response = await fetch(`http://127.0.0.1:7777/v1/index/status/${taskId}`);
    
    if (!response.ok) {
      throw new Error(`Failed to get index status: ${response.statusText}`);
    }
    
    return await response.json();
  },

  /**
   * Clear repository index
   */
  async clearIndex(repoName: string, confirmed: boolean): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`http://127.0.0.1:7777/v1/repos/${repoName}/index?confirmed=${confirmed}`, {
      method: 'DELETE'
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to clear index: ${response.statusText}`);
    }
    
    return await response.json();
  },

  /**
   * Poll for index status updates
   */
  async pollIndexStatus(taskId: string, onUpdate: (status: IndexStatus) => void, intervalMs = 2000): Promise<void> {
    return new Promise((resolve, reject) => {
      const pollInterval = setInterval(async () => {
        try {
          const status = await this.getIndexStatus(taskId);
          onUpdate(status);
          
          // Stop polling if task is complete or failed
          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(pollInterval);
            resolve();
          }
        } catch (error) {
          clearInterval(pollInterval);
          reject(error);
        }
      }, intervalMs);
    });
  }
};