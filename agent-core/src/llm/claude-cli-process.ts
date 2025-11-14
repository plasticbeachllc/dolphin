// agent-core/src/llm/claude-cli-process.ts
import { spawn } from "child_process";
import * as readline from "readline";
import type Anthropic from "@anthropic-ai/sdk";

export interface ClaudeCLIOptions {
  systemPrompt: string;
  messages: Anthropic.Messages.MessageParam[];
  model?: string;
  maxOutputTokens?: number;
  cwd?: string;
  timeout?: number;
}

// Response types matching Kilocode's ClaudeCodeMessage types
export type ClaudeCodeMessage =
  | {
      type: "system";
      subtype: "init";
      session_id: string;
      tools: string[];
      mcp_servers: string[];
      apiKeySource: "none" | "/login managed key" | string;
    }
  | {
      type: "assistant";
      message: Anthropic.Messages.Message;
      session_id: string;
    }
  | {
      type: "error";
    }
  | {
      type: "result";
      subtype: "success";
      total_cost_usd: number;
      is_error: boolean;
      duration_ms: number;
      duration_api_ms: number;
      num_turns: number;
      result: string;
      session_id: string;
    };

export interface ClaudeCLIResponse {
  content: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens?: number;
    cache_write_tokens?: number;
  };
  stop_reason?: string;
  isPaidUsage: boolean;
  totalCostUsd?: number;
}

/**
 * Runs Claude Code CLI process and returns streaming responses
 * Implementation based on Kilocode's approach
 */
export async function* runClaudeCode(
  options: ClaudeCLIOptions
): AsyncGenerator<ClaudeCodeMessage | string> {
  const {
    systemPrompt,
    messages,
    model = "claude-sonnet-4-20250514",
    maxOutputTokens = 16000,
    cwd,
    timeout: _timeout = 600000, // 10 minutes like Kilocode
  } = options;

  // Build CLI arguments (matching Kilocode's implementation)
  const args = [
    "-p", // Programmatic mode
    "--system-prompt",
    systemPrompt,
    "--verbose",
    "--output-format",
    "stream-json",
    "--disallowedTools",
    [
      "Task",
      "Bash",
      "Glob",
      "Grep",
      "LS",
      "exit_plan_mode",
      "Read",
      "Edit",
      "MultiEdit",
      "Write",
      "NotebookRead",
      "NotebookEdit",
      "WebFetch",
      "TodoRead",
      "TodoWrite",
      "WebSearch",
      "ExitPlanMode",
      "BashOutput",
      "KillBash",
    ].join(","),
    "--max-turns",
    "1", // Dolphin handles recursion
  ];

  if (model) {
    args.push("--model", model);
  }

  // Spawn Claude process without ANTHROPIC_API_KEY
  // (Let CLI use subscription mode)
  const env = { ...process.env };
  delete env.ANTHROPIC_API_KEY; // Remove API key to force subscription mode

  const child = spawn("claude", args, {
    stdio: ["pipe", "pipe", "pipe"],
    cwd: cwd || process.cwd(),
    env: {
      ...env,
      CLAUDE_CODE_MAX_OUTPUT_TOKENS: maxOutputTokens.toString(),
    },
  });

  // Track process state
  const processState = {
    partialData: null as string | null,
    error: null as Error | null,
    stderrLogs: "",
    exitCode: null as number | null,
  };

  // Setup readline for line-by-line parsing
  const rl = readline.createInterface({
    input: child.stdout,
  });

  try {
    // Handle stderr
    child.stderr.setEncoding("utf-8");
    child.stderr.on("data", (data) => {
      processState.stderrLogs += data.toString();
    });

    // Handle process close
    child.on("close", (code) => {
      processState.exitCode = code;
    });

    // Handle process errors
    child.on("error", (err) => {
      processState.error = err;
      rl.close();
    });

    // Write messages to stdin
    setImmediate(() => {
      try {
        child.stdin.write(JSON.stringify(messages), "utf8", (error) => {
          if (error) {
            console.error("Error writing to Claude Code stdin:", error);
            child.kill();
          }
        });
        child.stdin.end();
      } catch (error) {
        console.error("Error accessing Claude Code stdin:", error);
        child.kill();
      }
    });

    // Parse streaming responses
    for await (const line of rl) {
      if (processState.error) {
        throw processState.error;
      }

      if (line.trim()) {
        const chunk = parseChunk(line, processState);
        if (chunk) {
          yield chunk;
        }
      }
    }

    // Check for errors
    if (processState.error) {
      throw processState.error;
    }

    // Handle partial data for assistant messages
    if (processState.partialData?.startsWith('{"type":"assistant"')) {
      yield processState.partialData;
    }

    // Check exit code
    const exitCode = processState.exitCode;
    if (exitCode !== null && exitCode !== 0) {
      const errorOutput = (processState.error as any)?.message || processState.stderrLogs?.trim();
      throw new Error(
        `Claude Code process exited with code ${exitCode}.${errorOutput ? ` Error output: ${errorOutput}` : ""}`
      );
    }
  } finally {
    rl.close();
    if (!child.killed) {
      child.kill();
    }
  }
}

function parseChunk(
  data: string,
  processState: { partialData: string | null }
): ClaudeCodeMessage | string | null {
  // If we have partial data, append to it
  if (processState.partialData) {
    processState.partialData += data;

    const chunk = attemptParseChunk(processState.partialData);

    if (!chunk) {
      return null;
    }

    processState.partialData = null;
    return chunk;
  }

  // Try to parse current data
  const chunk = attemptParseChunk(data);

  if (!chunk) {
    processState.partialData = data;
  }

  return chunk;
}

function attemptParseChunk(data: string): ClaudeCodeMessage | null {
  try {
    return JSON.parse(data);
  } catch (error) {
    return null;
  }
}

/**
 * Higher-level interface that collects streaming responses into a single result
 */
export async function executeClaudeCode(options: ClaudeCLIOptions): Promise<ClaudeCLIResponse> {
  let content = "";
  let usage = {
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
  };
  let stop_reason: string | undefined;
  let isPaidUsage = true;
  let totalCostUsd = 0;

  for await (const chunk of runClaudeCode(options)) {
    // Handle string chunks (shouldn't happen with stream-json format, but just in case)
    if (typeof chunk === "string") {
      content += chunk;
      continue;
    }

    // Handle init message (detects auth mode)
    if (chunk.type === "system" && chunk.subtype === "init") {
      isPaidUsage = chunk.apiKeySource !== "none";
      continue;
    }

    // Handle assistant message (contains response)
    if (chunk.type === "assistant" && "message" in chunk) {
      const message = chunk.message;

      // Extract content
      for (const contentBlock of message.content) {
        if (contentBlock.type === "text") {
          content += contentBlock.text;
        }
      }

      // Update usage
      usage.input_tokens += message.usage.input_tokens;
      usage.output_tokens += message.usage.output_tokens;
      usage.cache_read_tokens =
        (usage.cache_read_tokens || 0) + ((message.usage as any).cache_read_input_tokens || 0);
      usage.cache_write_tokens =
        (usage.cache_write_tokens || 0) + ((message.usage as any).cache_creation_input_tokens || 0);

      stop_reason = message.stop_reason || undefined;
      continue;
    }

    // Handle result message (contains cost)
    if (chunk.type === "result" && "result" in chunk) {
      totalCostUsd = isPaidUsage ? chunk.total_cost_usd : 0;
    }
  }

  return {
    content,
    usage,
    stop_reason,
    isPaidUsage,
    totalCostUsd,
  };
}
