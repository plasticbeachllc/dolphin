// agent-core/src/llm/claude-cli-detector.ts
import { spawn } from "child_process";

/**
 * Execute a command with timeout
 */
const execCommand = (
  command: string,
  timeoutMs: number = 5000
): Promise<{ stdout: string; stderr: string }> => {
  return new Promise((resolve, reject) => {
    const args = command.split(" ");
    const cmd = args[0];
    const cmdArgs = args.slice(1);

    const proc = spawn(cmd, cmdArgs, {
      shell: false,
      timeout: timeoutMs,
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timeout = setTimeout(() => {
      timedOut = true;
      proc.kill();
      reject(new Error(`Command timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    proc.stdout?.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr?.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      clearTimeout(timeout);
      if (timedOut) return;

      if (code !== 0) {
        reject(new Error(`Command failed with code ${code}`));
      } else {
        resolve({ stdout, stderr });
      }
    });

    proc.on("error", (error) => {
      clearTimeout(timeout);
      if (!timedOut) {
        reject(error);
      }
    });
  });
};

/**
 * Detects Claude Code CLI installation and authentication status
 */
export class ClaudeCLIDetector {
  /**
   * Check if Claude Code CLI is installed
   */
  async isInstalled(): Promise<boolean> {
    try {
      const { stdout } = await execCommand("which claude");
      return stdout.trim().length > 0;
    } catch {
      // Try alternative detection methods for Windows
      try {
        await execCommand("claude --version");
        return true;
      } catch {
        return false;
      }
    }
  }

  /**
   * Get Claude CLI version
   */
  async getVersion(): Promise<string | null> {
    try {
      const { stdout } = await execCommand("claude --version");
      return stdout.trim();
    } catch {
      return null;
    }
  }

  /**
   * Check if user is authenticated with Claude Code
   * This assumes that if the CLI is installed, it's authenticated
   * (users must authenticate interactively the first time they run `claude`)
   */
  async isAuthenticated(): Promise<boolean> {
    // If CLI is installed, assume it's authenticated
    // The actual auth check happens when we spawn the process
    // If not authenticated, the CLI will return an error message
    return await this.isInstalled();
  }

  /**
   * Get authentication method (subscription vs API key)
   */
  async getAuthMethod(): Promise<"subscription" | "api_key" | "none"> {
    // Check if ANTHROPIC_API_KEY env var is set
    if (process.env.ANTHROPIC_API_KEY) {
      return "api_key";
    }

    const isAuth = await this.isAuthenticated();
    return isAuth ? "subscription" : "none";
  }

  /**
   * Check if CLI will use API key (even if subscription exists)
   * This happens when ANTHROPIC_API_KEY is set - CLI prioritizes it
   */
  async willUseAPIKey(): Promise<boolean> {
    return !!process.env.ANTHROPIC_API_KEY;
  }

  /**
   * Get complete authentication status
   */
  async getStatus(): Promise<{
    cliInstalled: boolean;
    cliVersion: string | null;
    cliAuthenticated: boolean;
    authMethod: "subscription" | "api_key" | "none";
    apiKeySet: boolean;
    willUseSubscription: boolean;
    warnings: string[];
  }> {
    const cliInstalled = await this.isInstalled();
    const cliVersion = cliInstalled ? await this.getVersion() : null;
    const cliAuthenticated = cliInstalled ? await this.isAuthenticated() : false;
    const authMethod = await this.getAuthMethod();
    const apiKeySet = !!process.env.ANTHROPIC_API_KEY;
    const willUseAPIKey = await this.willUseAPIKey();
    const willUseSubscription = cliAuthenticated && !willUseAPIKey;

    const warnings: string[] = [];

    // Warning: User has subscription but will use API due to env var
    if (cliAuthenticated && willUseAPIKey) {
      warnings.push("ANTHROPIC_API_KEY is set. CLI will use API billing instead of subscription.");
      warnings.push("To use subscription: unset ANTHROPIC_API_KEY");
    }

    // Warning: CLI not installed
    if (!cliInstalled) {
      warnings.push("Claude Code CLI not installed. Using API mode only.");
      warnings.push("Install with: npm install -g @anthropic-ai/claude-code");
    }

    // Warning: CLI installed but not authenticated
    if (cliInstalled && !cliAuthenticated && !apiKeySet) {
      warnings.push("Claude CLI not authenticated and no API key set.");
      warnings.push(
        'Authenticate with: claude (then select "1. Claude account with subscription")'
      );
    }

    return {
      cliInstalled,
      cliVersion,
      cliAuthenticated,
      authMethod,
      apiKeySet,
      willUseSubscription,
      warnings,
    };
  }
}
