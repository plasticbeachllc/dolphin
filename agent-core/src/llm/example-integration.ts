// agent-core/src/llm/example-integration.ts
// Example of how to integrate ClaudeCLIDetector into AgentCore

import { ClaudeCLIDetector } from "./claude-cli-detector";

/**
 * Example: Initialize auth detection on AgentCore startup
 */
export async function initializeAuthDetection(): Promise<void> {
  const detector = new ClaudeCLIDetector();
  
  console.error("[Agent Core] Detecting Claude authentication...");
  
  const status = await detector.getStatus();
  
  // Log the complete status
  console.error("\n📊 Authentication Status:");
  console.error(`  CLI Installed: ${status.cliInstalled}`);
  console.error(`  CLI Version: ${status.cliVersion || "N/A"}`);
  console.error(`  CLI Authenticated: ${status.cliAuthenticated}`);
  console.error(`  Auth Method: ${status.authMethod}`);
  console.error(`  API Key Set: ${status.apiKeySet}`);
  console.error(`  Will Use Subscription: ${status.willUseSubscription}`);
  
  // Display warnings if any
  if (status.warnings.length > 0) {
    console.error("\n⚠️  Authentication Warnings:");
    status.warnings.forEach((warning) => {
      console.error(`  - ${warning}`);
    });
  }
  
  // Determine which mode to use
  if (status.willUseSubscription) {
    console.error("\n✅ Using Claude subscription (no API costs)");
  } else if (status.apiKeySet) {
    console.error("\n💳 Using API key (pay-per-token billing)");
  } else {
    console.error("\n❌ No authentication configured");
    console.error("   Install Claude CLI or set ANTHROPIC_API_KEY");
  }
  
  console.error("");
}

/**
 * Example: Add to AgentCore constructor
 */
export class AgentCoreWithAuth {
  private authDetector: ClaudeCLIDetector;
  
  constructor() {
    this.authDetector = new ClaudeCLIDetector();
  }
  
  async start() {
    // Check auth status on startup
    const status = await this.authDetector.getStatus();
    
    // Store for later use
    this.logAuthStatus(status);
    
    // Continue with rest of startup...
  }
  
  private logAuthStatus(status: Awaited<ReturnType<typeof this.authDetector.getStatus>>) {
    console.error("[Agent Core] Auth Status:", {
      mode: status.authMethod,
      willUseSubscription: status.willUseSubscription,
      warnings: status.warnings.length,
    });
  }
  
  /**
   * Expose auth status to extension via JSON-RPC
   */
  async handleGetAuthStatus(): Promise<any> {
    return await this.authDetector.getStatus();
  }
}

/**
 * Example: Integration point in main.ts
 * 
 * Add to AgentCore class:
 * 
 * ```typescript
 * import { ClaudeCLIDetector } from "./llm/claude-cli-detector";
 * 
 * class AgentCore {
 *   private authDetector: ClaudeCLIDetector;
 *   
 *   constructor(workspaceRoot: string) {
 *     this.workspaceRoot = workspaceRoot;
 *     this.authDetector = new ClaudeCLIDetector();
 *     // ... rest of constructor
 *   }
 *   
 *   async start() {
 *     // ... existing startup code ...
 *     
 *     // Add auth detection
 *     const authStatus = await this.authDetector.getStatus();
 *     console.error("[Agent Core] Auth Status:", authStatus);
 *     
 *     if (authStatus.warnings.length > 0) {
 *       authStatus.warnings.forEach(w => console.error(`[Auth Warning] ${w}`));
 *     }
 *     
 *     // ... continue with rest of startup ...
 *   }
 *   
 *   private handleMessage(data: string) {
 *     // ... existing code ...
 *     
 *     // Add handler for get_auth_status
 *     if (message.method === "get_auth_status") {
 *       this.handleGetAuthStatus(message);
 *     }
 *   }
 *   
 *   private async handleGetAuthStatus(message: Message) {
 *     const status = await this.authDetector.getStatus();
 *     
 *     const response: Message = {
 *       jsonrpc: "2.0",
 *       id: message.id,
 *       result: status,
 *     };
 *     
 *     process.stdout.write(JSON.stringify(response) + "\n");
 *   }
 * }
 * ```
 */