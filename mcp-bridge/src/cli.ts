#!/usr/bin/env bun
import { createServer } from "./mcp/server.js";
import { getOrCreateKbApiKey } from "../../shared/kb-auth";
import { CONFIG } from "./util/config.js";

const DOLPHIN_API_URL = CONFIG.DOLPHIN_API_URL;
const LOG_LEVEL = CONFIG.LOG_LEVEL;
const SERVER_NAME = CONFIG.SERVER_NAME;
const SERVER_VERSION = CONFIG.SERVER_VERSION;

// Validate critical configuration
if (!DOLPHIN_API_URL || DOLPHIN_API_URL.trim() === "") {
  console.error("❌ Error: DOLPHIN_API_URL or KB_REST_BASE_URL environment variable is required");
  console.error("   Example: DOLPHIN_API_URL=http://127.0.0.1:7777");
  process.exit(1);
}

// Validate URL format
try {
  new URL(DOLPHIN_API_URL);
} catch {
  console.error("❌ Error: Invalid DOLPHIN_API_URL format");
  console.error(`   Current value: ${DOLPHIN_API_URL}`);
  console.error("   Expected format: http://127.0.0.1:7777 or https://api.example.com");
  process.exit(1);
}

// Ensure KB API key is available (official entry point for pure MCP setups)
if (!process.env.DOLPHIN_API_KEY && !process.env.DOLPHIN_KB_API_KEY) {
  try {
    const key = getOrCreateKbApiKey();
    process.env.DOLPHIN_API_KEY = key;
    process.env.DOLPHIN_KB_API_KEY = key;
  } catch (error: unknown) {
    console.warn(
      "⚠️  Warning: Failed to initialize KB API key:",
      error instanceof Error ? error.message : String(error)
    );
    console.warn("   Secured KB endpoints may reject requests.");
  }
}

// Set process environment for the server
process.env.DOLPHIN_API_URL = DOLPHIN_API_URL;
process.env.LOG_LEVEL = LOG_LEVEL;
process.env.SERVER_NAME = SERVER_NAME;
process.env.SERVER_VERSION = SERVER_VERSION;

// Start the server
try {
  await createServer();
} catch (error: unknown) {
  const errorMessage = error instanceof Error ? error.message : String(error);
  console.error("❌ Failed to start Dolphin MCP server:", errorMessage);
  process.exit(1);
}
