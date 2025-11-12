// vscode-extension/webview/src/lib/api/kb-api.ts
import { getVSCodeAPI } from './vscode';

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

export interface RegisterRepoRequest {
  name: string;
  path: string;
  default_embed_model?: string;
}

export interface RegisterRepoResponse {
  repo_id: number;
  name: string;
  path: string;
  message: string;
}

/**
 * Send a KB request to the extension host and wait for response
 */
function sendKbRequest<T = any>(type: string, params: any = {}): Promise<T> {
  return new Promise((resolve, reject) => {
    const requestId = `kb_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    console.log(`[kb-api] Sending request: ${type} with requestId: ${requestId}`, params);
    
    // Set up response handler
    const handler = (event: MessageEvent) => {
      const message = event.data;
      console.log(`[kb-api] Received message for requestId ${requestId}:`, message);
      
      if (message.type === `${type}_response` && message.requestId === requestId) {
        console.log(`[kb-api] Match! Processing response for ${type}`);
        window.removeEventListener('message', handler);
        
        if (message.error) {
          console.error(`[kb-api] Request ${type} failed:`, message.error);
          reject(new Error(message.error));
        } else {
          console.log(`[kb-api] Request ${type} succeeded with data:`, message.data);
          resolve(message.data);
        }
      }
    };
    
    window.addEventListener('message', handler);
    
    // Send request
    const vscode = getVSCodeAPI();
    vscode.postMessage({
      type,
      requestId,
      ...params
    });
    
    // Timeout after 30 seconds
    setTimeout(() => {
      window.removeEventListener('message', handler);
      console.error(`[kb-api] Request ${type} (${requestId}) timed out after 30s`);
      reject(new Error(`KB request timeout: ${type}`));
    }, 30000);
  });
}

/**
 * KB API client for interacting with the Knowledge Base backend
 * Uses VSCode postMessage pattern instead of direct fetch
 */
export const kbApi = {
  /**
   * Register a new repository in the knowledge base
   */
  async registerRepo(request: RegisterRepoRequest): Promise<RegisterRepoResponse> {
    return sendKbRequest<RegisterRepoResponse>('kb_register_repo', request);
  },

  /**
   * Get repository statistics
   */
  async getRepoStats(repoName: string): Promise<RepoStats> {
    return sendKbRequest<RepoStats>('kb_get_stats', { repoName });
  },

  /**
   * Trigger a reindex operation
   */
  async triggerReindex(repoName: string, request: ReindexRequest): Promise<ReindexResponse> {
    return sendKbRequest<ReindexResponse>('kb_trigger_reindex', { repoName, request });
  },

  /**
   * Get indexing task status
   */
  async getIndexStatus(taskId: string): Promise<IndexStatus> {
    return sendKbRequest<IndexStatus>('kb_get_status', { taskId });
  },

  /**
   * Clear repository index
   */
  async clearIndex(repoName: string, confirmed: boolean): Promise<{ success: boolean; message: string }> {
    return sendKbRequest('kb_clear_index', { repoName, confirmed });
  },

  /**
   * Poll for index status updates
   */
  async pollIndexStatus(taskId: string, onUpdate: (status: IndexStatus) => void, intervalMs = 2000): Promise<void> {
    return new Promise((resolve, reject) => {
      let errorCount = 0;
      const MAX_ERRORS = 3;
      
      const poll = async () => {
        try {
          const status = await this.getIndexStatus(taskId);
          errorCount = 0; // Reset error count on success
          onUpdate(status);
          
          // Stop polling if task is complete or failed
          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(pollInterval);
            resolve();
          }
        } catch (error) {
          console.error('[kb-api] Error polling status:', error);
          errorCount++;
          
          // Only stop polling after multiple consecutive errors
          if (errorCount >= MAX_ERRORS) {
            clearInterval(pollInterval);
            reject(error);
          }
        }
      };
      
      // Poll immediately, then set up interval
      poll();
      const pollInterval = setInterval(poll, intervalMs);
    });
  }
};