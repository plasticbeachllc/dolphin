import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { restListRepos } from "../rest/client.js";
import type { makeSearchKnowledge } from "../mcp/tools/search_knowledge.js";
import type { makeFetchChunk } from "../mcp/tools/fetch_chunk.js";
import type { makeFetchLines } from "../mcp/tools/fetch_lines.js";
import type { makeGetVectorStoreInfo } from "../mcp/tools/get_vector_store_info.js";

export interface BridgeSmokeDeps {
  listRepos: typeof restListRepos;
  makeSearchKnowledge: typeof makeSearchKnowledge;
  makeFetchChunk: typeof makeFetchChunk;
  makeFetchLines: typeof makeFetchLines;
  makeGetVectorStoreInfo: typeof makeGetVectorStoreInfo;
}

export interface BridgeSmokeOptions {
  query?: string;
  log?: (message: string) => void;
}

export interface BridgeSmokeReportEntry {
  name: string;
  status: "passed" | "failed";
  duration_ms: number;
  error?: string;
}

export interface BridgeSmokeReport {
  entries: BridgeSmokeReportEntry[];
  passed: number;
  failed: number;
}

interface SearchHitSummary {
  chunk_id: string;
  repo: string;
  path: string;
  start_line: number;
  end_line: number;
}

function isTextBlock(
  block: CallToolResult["content"][number]
): block is CallToolResult["content"][number] & { type: "text"; text: string } {
  return block.type === "text";
}

function parseHitsJson(content: CallToolResult["content"]): { hits?: SearchHitSummary[] } | null {
  const jsonBlock = content?.find((block) => isTextBlock(block) && block.text.includes("```json"));
  if (!jsonBlock?.text) return null;
  const match = jsonBlock.text.match(/```json\n([\s\S]*?)\n```/);
  if (!match) return null;
  return JSON.parse(match[1]) as { hits?: SearchHitSummary[] };
}

function formatError(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (typeof err === "object" && err && "error" in err) {
    const errWithCode = err as { error: { code?: string; message?: string } };
    const pieces = [errWithCode.error.code, errWithCode.error.message].filter(Boolean);
    return pieces.join(": ") || "unknown upstream error";
  }
  return String(err);
}

export async function runBridgeSmokeSuite(
  deps: BridgeSmokeDeps,
  options?: BridgeSmokeOptions
): Promise<BridgeSmokeReport> {
  const log = options?.log ?? (() => {});
  const entries: BridgeSmokeReportEntry[] = [];
  let firstHit: SearchHitSummary | undefined;

  const steps: Array<{
    name: string;
    run: () => Promise<void>;
  }> = [
    {
      name: "REST API connectivity",
      run: async () => {
        const repos = await deps.listRepos();
        log(`Found ${repos.repos.length} indexed repo(s)`);
        if (repos.repos.length === 0) {
          throw new Error(
            "No repositories indexed. Index a repo before running the bridge smoke test."
          );
        }
      },
    },
    {
      name: "store.info",
      run: async () => {
        const { handler } = deps.makeGetVectorStoreInfo();
        const result = (await handler({}, undefined)) as CallToolResult;
        if (result.isError) {
          throw new Error(result.content?.[0]?.text ?? "store.info returned an error");
        }
      },
    },
    {
      name: "search",
      run: async () => {
        const { handler } = deps.makeSearchKnowledge();
        const result = (await handler({
          input: { query: options?.query ?? "function", top_k: 3 },
        })) as CallToolResult;

        if (result.isError) {
          throw new Error(result.content?.[0]?.text ?? "search returned an error");
        }

        const hits = parseHitsJson(result.content)?.hits ?? [];
        if (hits.length === 0) {
          throw new Error("search returned no hits to follow up on");
        }
        firstHit = hits[0];
      },
    },
    {
      name: "chunk.get",
      run: async () => {
        if (!firstHit) {
          throw new Error("Cannot fetch chunk before search returns hits");
        }
        const { handler } = deps.makeFetchChunk();
        const result = (await handler({
          input: { chunk_id: firstHit.chunk_id },
        })) as CallToolResult;

        if (result.isError) {
          throw new Error(result.content?.[0]?.text ?? "chunk.get returned an error");
        }
      },
    },
    {
      name: "file.lines",
      run: async () => {
        if (!firstHit) {
          throw new Error("Cannot fetch lines before search returns hits");
        }
        const { handler } = deps.makeFetchLines();
        const result = (await handler({
          input: {
            repo: firstHit.repo,
            path: firstHit.path,
            start: firstHit.start_line,
            end: Math.min(firstHit.start_line + 10, firstHit.end_line),
          },
        })) as CallToolResult;

        if (result.isError) {
          throw new Error(result.content?.[0]?.text ?? "file.lines returned an error");
        }
      },
    },
  ];

  for (const step of steps) {
    const started = Date.now();
    try {
      await step.run();
      entries.push({ name: step.name, status: "passed", duration_ms: Date.now() - started });
      log(`✅ ${step.name}`);
    } catch (err) {
      const message = formatError(err);
      entries.push({
        name: step.name,
        status: "failed",
        duration_ms: Date.now() - started,
        error: message,
      });
      log(`❌ ${step.name}: ${message}`);
      break;
    }
  }

  const passed = entries.filter((entry) => entry.status === "passed").length;
  const failed = entries.length - passed;

  return { entries, passed, failed };
}
