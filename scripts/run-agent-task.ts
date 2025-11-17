#!/usr/bin/env bun
import { spawn } from "bun";
import { join, resolve } from "path";

const [, , messageArg, modeArg, workspaceArg] = process.argv;
const message = messageArg ?? "Plan a simple dashboard UI for my validation suite";
const mode = modeArg ?? "architect";
const workspaceRoot = workspaceArg ? resolve(workspaceArg) : process.cwd();

const agentCorePath = join(process.cwd(), "agent-core");
console.log(`[runner] launching Agent Core from ${agentCorePath}`);
console.log(`[runner] workspace root: ${workspaceRoot}`);

const child = spawn({
  cmd: ["bun", "run", "src/main.ts", workspaceRoot],
  cwd: agentCorePath,
  stdin: "pipe",
  stdout: "pipe",
  stderr: "inherit",
  env: process.env,
});

async function startStdoutReader() {
  if (!child.stdout) {
    console.warn("[runner] child stdout unavailable");
    return;
  }
  const reader = child.stdout.getReader();
  while (true) {
    const { value, done } = await reader.read();
    if (done || !value) {
      break;
    }
    stdoutBuffer = Buffer.concat([stdoutBuffer, Buffer.from(value)]);
    processStdoutBuffer();
  }
}

let stdoutBuffer = Buffer.alloc(0);
function processStdoutBuffer() {
  const delimiter = Buffer.from("\r\n\r\n");
  while (stdoutBuffer.length > 0) {
    const headerEnd = stdoutBuffer.indexOf(delimiter);
    if (headerEnd === -1) {
      return;
    }
    const header = stdoutBuffer.slice(0, headerEnd).toString("utf-8");
    const match = header.match(/Content-Length:\s*(\d+)/i);
    if (!match) {
      console.log(`[agent stdout] ${stdoutBuffer.toString("utf-8")}`);
      stdoutBuffer = Buffer.alloc(0);
      return;
    }
    const contentLength = Number.parseInt(match[1], 10);
    const totalLength = headerEnd + delimiter.length + contentLength;
    if (stdoutBuffer.length < totalLength) {
      return;
    }
    const body = stdoutBuffer
      .slice(headerEnd + delimiter.length, totalLength)
      .toString("utf-8");
    stdoutBuffer = stdoutBuffer.slice(totalLength);
    try {
      const parsed = JSON.parse(body);
      console.log("[agent response]", JSON.stringify(parsed, null, 2));
    } catch (error) {
      console.log("[agent raw response]", body);
    }
  }
}

function sendTask() {
  const request = {
    id: 1,
    method: "send_message",
    params: {
      message,
      mode,
      context: {},
    },
  };
  const body = JSON.stringify(request);
  const payload = `Content-Length: ${Buffer.byteLength(body, "utf-8")}\r\n\r\n${body}`;
  child.stdin.write(payload);
  console.log(`[runner] sent ${mode} request: ${message}`);
}

child.exited.then((code) => {
  console.log(`[runner] agent exited with code ${code}`);
  process.exit(code ?? 0);
});

startStdoutReader().catch((error) => {
  console.error("[runner] stdout reader failed", error);
});

setTimeout(sendTask, 1000);
