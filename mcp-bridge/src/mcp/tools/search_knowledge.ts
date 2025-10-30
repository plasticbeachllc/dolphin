import type { Tool, CallToolResult, EmbeddedResource, TextContent } from '@modelcontextprotocol/sdk/types.js'
import { z } from 'zod'
import { zodToJsonSchema } from 'zod-to-json-schema'
import { restSearch, type SearchResponse } from '../../rest/client.js'
import { mimeFromLangOrPath } from '../../util/mime.js'
import { jsonSizeBytes } from '../../util/payloadCap.js'
import { logInfo, logWarn, logError } from '../../util/logger.js'

const INPUT_SHAPE = {
  query: z.string().min(1),
  repos: z.array(z.string()).optional(),
  path_prefix: z.array(z.string()).optional(),
  top_k: z.number().int().min(1).max(100).optional(),
  max_snippets: z.number().int().min(1).optional(),
  deadline_ms: z.number().int().min(50).optional(),
  embed_model: z.enum(['small', 'large']).optional().default('small'),
  score_cutoff: z.number().optional(),
  cursor: z.string().optional()
}

const INPUT = z.object(INPUT_SHAPE)

type Input = z.infer<typeof INPUT>

const CAP_BYTES = 50 * 1024
const PER_SNIPPET_CHAR_CAP = 500
const SHRUNK_SNIPPET_CHAR_CAP = 300
const MIN_SNIPPET_CHAR_FLOOR = 200

import { fenceLang } from '../../util/language.js'

function buildPromptReady (res: SearchResponse): string {
  const parts: string[] = []
  for (const h of res.hits) {
    parts.push(`[${h.repo}] ${h.path}#L${h.start_line}-L${h.end_line}`)
    const lang = fenceLang(h.lang, h.path)
    const code = h.snippet ?? ''
    if (lang) {
      parts.push('```' + lang)
      parts.push(code)
      parts.push('```')
    } else {
      parts.push('```')
      parts.push(code)
      parts.push('```')
    }
  }
  return parts.join('\n') + (parts.length ? '\n' : '')
}

export function makeSearchKnowledge (): { definition: Tool, handler: any, inputSchema: typeof INPUT_SHAPE } {
  const definition: Tool = {
    name: 'search_knowledge',
    description: 'Query code and docs across indexed repositories and return ranked snippets with citations.',
    inputSchema: zodToJsonSchema(INPUT) as any,
    annotations: {
      title: 'Search Knowledge Base',
      readOnlyHint: true,
      openWorldHint: false
    }
  }

  const handler = async (args: any, signal?: AbortSignal): Promise<CallToolResult> => {
    const started = Date.now()
    try {
      const input = INPUT.parse(args?.input ?? args)

      // Trim repo names only
      const repos = input.repos?.map(r => r.trim())

      const body = {
        query: input.query,
        repos,
        path_prefix: input.path_prefix,
        top_k: input.top_k,
        max_snippets: input.max_snippets,
        deadline_ms: input.deadline_ms,
        embed_model: input.embed_model,
        score_cutoff: input.score_cutoff,
        cursor: input.cursor,
        include_prompt_ready: false
      }

      const res: SearchResponse = await restSearch(body, signal)

      // Build summary
      const k = res.hits.length
      const reposSet = new Set(res.hits.map(h => h.repo))
      const rcount = reposSet.size
      const est = res.meta.estimated_total
      const more = res.meta.complete === false && res.meta.cursor
      const summaryParts = [
        `Found ${k} result${k === 1 ? '' : 's'}${rcount > 0 ? ` across ${rcount} repo${rcount === 1 ? '' : 's'}` : ''}.`
      ]
      if (typeof est === 'number') summaryParts.push(`~${est} estimated results.`)
      if (more) summaryParts.push('More available — call search_knowledge again with cursor.')
      const summary = summaryParts.join(' ')

      // Build prompt-ready text
      let promptReady = buildPromptReady(res)

      // Build content blocks: one text summary + prompt-ready + resource blocks for each hit
      const content: CallToolResult['content'] = []
      content.push({ type: 'text', text: summary } as TextContent)
      if (promptReady.length > 0) {
        content.push({ type: 'text', text: promptReady } as TextContent)
      }

      for (const hit of res.hits) {
        const includeText = (hit.snippet ?? '').length <= PER_SNIPPET_CHAR_CAP
        const resource: EmbeddedResource = {
          uri: hit.resource_link,
          mimeType: mimeFromLangOrPath(hit.lang, hit.path),
          text: includeText ? hit.snippet : undefined
        }
        content.push({ type: 'resource', resource })
      }

      // _meta compact hits list
      const metaHits = res.hits.map(h => ({
        chunk_id: h.chunk_id,
        repo: h.repo,
        path: h.path,
        start_line: h.start_line,
        end_line: h.end_line,
        score: h.score
      }))

      const result: CallToolResult = {
        content,
        isError: false,
        _meta: {
          hits: metaHits,
          cursor: res.meta.cursor,
          estimated_total: res.meta.estimated_total,
          complete: res.meta.complete,
          warnings: res.meta.warnings,
          model: res.meta.model,
          top_k: res.meta.top_k,
          mcp_latency_ms: Date.now() - started
        }
      }

      // Enforce ~50KB total cap by trimming in specified order
      let size = jsonSizeBytes(result)

      // Step 1: Trim prompt_ready text to fit budget
      if (size > CAP_BYTES) {
        const prIndex = content.length > 1 && (content[1] as any)?.type === 'text' ? 1 : -1
        if (prIndex === 1) {
          let prText = (content[1] as TextContent).text
          // Iteratively trim promptReady by 10% until under cap or floor
          while (prText.length > 0 && size > CAP_BYTES) {
            const cut = Math.max(Math.floor(prText.length * 0.9), 0)
            prText = prText.slice(0, cut)
            ;(content[1] as TextContent).text = prText
            size = jsonSizeBytes(result)
          }
        }
      }

      // Step 2: Shrink per-snippet windows (reduce text length) toward a floor
      if (size > CAP_BYTES) {
        // First pass: cap each resource text to SHRUNK_SNIPPET_CHAR_CAP
        for (let i = 0; i < content.length && size > CAP_BYTES; i++) {
          const block = content[i]
          if (block.type === 'resource' && block.resource?.text) {
            const txt = block.resource.text
            if (txt.length > SHRUNK_SNIPPET_CHAR_CAP) {
              block.resource.text = txt.slice(0, SHRUNK_SNIPPET_CHAR_CAP)
              size = jsonSizeBytes(result)
            }
          }
        }
        // Second pass: cap further to MIN_SNIPPET_CHAR_FLOOR if still too big
        for (let i = 0; i < content.length && size > CAP_BYTES; i++) {
          const block = content[i]
          if (block.type === 'resource' && block.resource?.text) {
            const txt = block.resource.text
            if (txt.length > MIN_SNIPPET_CHAR_FLOOR) {
              block.resource.text = txt.slice(0, MIN_SNIPPET_CHAR_FLOOR)
              size = jsonSizeBytes(result)
            }
          }
        }
      }

      // Step 3: Remove snippet text from lowest-scoring hits first (keep citations)
      if (size > CAP_BYTES) {
        for (let i = res.hits.length - 1; i >= 0 && size > CAP_BYTES; i--) {
          const blockIdx = i + 2 // +2 to skip summary and promptReady
          const block = result.content[blockIdx]
          if (block?.type === 'resource' && block.resource?.text) {
            delete (block.resource as any).text
            size = jsonSizeBytes(result)
          }
        }
      }

      // Step 4: Drop lowest-scoring citations entirely
      if (size > CAP_BYTES) {
        while (result.content.length > 1 && size > CAP_BYTES) {
          // Keep summary at index 0; attempt to keep promptReady at index 1 if present
          const dropIndex = result.content.length - 1
          // pop content and its meta hit
          result.content.pop()
          metaHits.pop()
          size = jsonSizeBytes(result)
        }
        // Mark as partial page when trimming occurred
        result._meta = { ...result._meta, complete: false }
        await logWarn('search', 'trimmed content to respect 50KB cap', { trimmed: true })
      }

      await logInfo('search', 'search_knowledge success', {
        hits_count: res.hits.length,
        warnings: res.meta.warnings,
        latency_ms: res.meta.latency_ms,
        mcp_latency_ms: Date.now() - started
      })

      return result
    } catch (e: any) {
      const err = e?.error ? e : { error: { code: 'unexpected_error', message: e?.message ?? String(e) } }
      await logError('search', 'search_knowledge error', { error_code: err.error.code, message: err.error.message })
      const message = `${err.error.message} Remediation: check repo names with /v1/repos, adjust filters, or increase deadline_ms/top_k.`
      const content: CallToolResult['content'] = [{ type: 'text', text: message }]
      return { content, isError: true, _meta: { upstream: err } }
    }
  }

  return { definition, handler, inputSchema: INPUT_SHAPE }
}
