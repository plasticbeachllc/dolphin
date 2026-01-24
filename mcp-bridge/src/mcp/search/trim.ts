import type { CallToolResult, TextContent } from "@modelcontextprotocol/sdk/types.js";
import { jsonSizeBytes } from "../../util/payloadCap.js";
import { logWarn } from "../../util/logger.js";
import type { HitsJson } from "./format.js";
import type { WarningEntry } from "./contracts.js";

export async function applyPayloadTrimming(params: {
  result: CallToolResult;
  hitsJson: HitsJson;
  includeHitsJson: boolean;
  promptReady: string;
  warningEntries: WarningEntry[];
  includeWarningsInText: boolean;
  capBytes: number;
  shrunkSnippetCharCap: number;
  minSnippetCharFloor: number;
  totalHits: number;
}): Promise<void> {
  const {
    result,
    hitsJson,
    includeHitsJson,
    promptReady,
    warningEntries,
    includeWarningsInText,
    capBytes,
    shrunkSnippetCharCap,
    minSnippetCharFloor,
    totalHits,
  } = params;

  const content = result.content ?? [];

  let size = jsonSizeBytes(result);

  const hitsJsonIndex = includeHitsJson ? 1 : -1;
  const promptReadyIndex = promptReady.length > 0 ? (includeHitsJson ? 2 : 1) : -1;

  if (size > capBytes) {
    if (promptReadyIndex >= 0 && content[promptReadyIndex]?.type === "text") {
      let prText: string = (content[promptReadyIndex] as TextContent).text;
      while (prText.length > 0 && size > capBytes) {
        const cut = Math.max(Math.floor(prText.length * 0.9), 0);
        prText = prText.slice(0, cut);
        (content[promptReadyIndex] as TextContent).text = prText;
        size = jsonSizeBytes(result);
      }
    }
  }

  if (size > capBytes && hitsJsonIndex >= 0 && content[hitsJsonIndex]?.type === "text") {
    while (hitsJson.hits.length > 1 && size > capBytes) {
      hitsJson.hits.pop();
      (content[hitsJsonIndex] as TextContent).text =
        "```json\n" + JSON.stringify(hitsJson) + "\n```";
      size = jsonSizeBytes(result);
    }
    if (size > capBytes && hitsJson.hits.length === 1) {
      (hitsJson.hits[0] as any).uris = {
        chunk: (hitsJson.hits[0] as any).uris.chunk,
        snippet: (hitsJson.hits[0] as any).uris.snippet,
      };
      (content[hitsJsonIndex] as TextContent).text =
        "```json\n" + JSON.stringify(hitsJson) + "\n```";
      size = jsonSizeBytes(result);
    }
  }

  if (size > capBytes) {
    for (let i = 0; i < content.length && size > capBytes; i++) {
      const block = content[i];
      if (
        block.type === "resource" &&
        "resource" in block &&
        block.resource &&
        "text" in block.resource
      ) {
        const txt = block.resource.text as string;
        if (txt.length > shrunkSnippetCharCap) {
          block.resource.text = txt.slice(0, shrunkSnippetCharCap);
          size = jsonSizeBytes(result);
        }
      }
    }

    for (let i = 0; i < content.length && size > capBytes; i++) {
      const block = content[i];
      if (
        block.type === "resource" &&
        "resource" in block &&
        block.resource &&
        "text" in block.resource
      ) {
        const txt = block.resource.text as string;
        if (txt.length > minSnippetCharFloor) {
          block.resource.text = txt.slice(0, minSnippetCharFloor);
          size = jsonSizeBytes(result);
        }
      }
    }
  }

  const resourceOffset = (() => {
    let offset = 1;
    if (includeHitsJson) offset += 1;
    if (promptReady.length > 0) offset += 1;
    return offset;
  })();

  if (size > capBytes) {
    for (let i = totalHits - 1; i >= 0 && size > capBytes; i--) {
      const blockIdx = i + resourceOffset;
      const block = result.content[blockIdx];
      if (
        block?.type === "resource" &&
        "resource" in block &&
        block.resource &&
        "text" in block.resource
      ) {
        block.resource.text = "";
        size = jsonSizeBytes(result);
      }
    }
  }

  if (size > capBytes) {
    while (result.content.length > 1 && size > capBytes) {
      result.content.pop();
      size = jsonSizeBytes(result);
    }

    result._meta = {
      ...result._meta,
      complete: false,
      warnings: Array.isArray(result._meta?.warnings)
        ? [...(result._meta?.warnings as string[]), "payload_trimmed"]
        : ["payload_trimmed"],
    };

    warningEntries.push({ code: "payload_trimmed" });

    if (includeHitsJson && hitsJsonIndex >= 0 && result.content[hitsJsonIndex]?.type === "text") {
      hitsJson.meta.warnings = warningEntries;
      (result.content[hitsJsonIndex] as TextContent).text =
        "```json\n" + JSON.stringify(hitsJson) + "\n```";
      size = jsonSizeBytes(result);
    }

    if (includeWarningsInText) {
      const txt = (result.content[0] as TextContent).text;
      const warningText = warningEntries
        .map((entry) => (entry.detail ? `${entry.code}(${entry.detail})` : entry.code))
        .join(", ");
      (result.content[0] as TextContent).text = txt.includes("payload_trimmed")
        ? txt
        : `${txt} Warnings: ${warningText}`;
    }

    await logWarn("search", "trimmed content to respect 70KB cap", { trimmed: true });
  }
}
