import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'

// Enhanced mock REST server for comprehensive unit tests
export function startMockRest (port = 7777): Promise<() => Promise<void>> {
  let repoCache = {
    repos: [
      { name: 'repoa', path: '/abs/repoa', default_embed_model: 'small', files: 1, chunks: 2 },
      { name: 'repob', path: '/abs/repob', default_embed_model: 'large', files: 3, chunks: 5 }
    ]
  }

  const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
    try {
      const url = new URL(req.url ?? '', `http://127.0.0.1:${port}`)
      
      // GET /v1/repos
      if (req.method === 'GET' && url.pathname === '/v1/repos') {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify(repoCache))
        return
      }

      // GET /v1/chunks/{id}
      if (req.method === 'GET' && url.pathname.startsWith('/v1/chunks/')) {
        const id = url.pathname.split('/').pop()
        
        // Simulate chunk not found
        if (id === 'not-found') {
          res.writeHead(404, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: { code: 'chunk_not_found', message: 'Chunk not found' } }))
          return
        }

        const body = { 
          chunk_id: id, 
          repo: 'repoa', 
          path: 'src/a.ts', 
          lang: 'typescript', 
          start_line: 1, 
          end_line: 10, 
          content: 'export const a = 1;\n// Some code here\nfunction test() {}\n', 
          resource_link: 'kb://repoa/src/a.ts#L1-L10' 
        }
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify(body))
        return
      }

      // GET /v1/file
      if (req.method === 'GET' && url.pathname === '/v1/file') {
        const path = url.searchParams.get('path') ?? 'src/a.ts'
        const start = Number(url.searchParams.get('start') ?? '1')
        const end = Number(url.searchParams.get('end') ?? '10')
        const repo = url.searchParams.get('repo') ?? 'repoa'

        // Simulate file not found
        if (path === 'nonexistent.ts') {
          res.writeHead(404, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: { code: 'file_not_found', message: 'File not found' } }))
          return
        }

        // Simulate invalid range
        if (start > end) {
          res.writeHead(400, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: { code: 'invalid_range', message: 'Invalid line range' } }))
          return
        }

        const body = { 
          repo, 
          path, 
          start_line: start, 
          end_line: end, 
          content: `// Lines ${start}-${end}\nconst content = 'slice';`,
          lang: path.endsWith('.ts') ? 'typescript' : path.endsWith('.py') ? 'python' : 'plain',
          source: 'disk' 
        }
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify(body))
        return
      }

      // POST /v1/search
      if (req.method === 'POST' && url.pathname === '/v1/search') {
        let raw = ''
        for await (const chunk of req) raw += chunk
        const body = JSON.parse(raw || '{}')
        const { query, repos, path_prefix, top_k, cursor, deadline_ms } = body

        // Simulate repo not found
        if (repos && repos.some((r: string) => r.trim() === 'nonexistent-repo')) {
          res.writeHead(404, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: { code: 'repo_not_found', message: 'Repository not found' } }))
          return
        }

        // Simulate deadline exceeded (partial results)
        if (deadline_ms === 1) {
          const partialHits = [
            { repo: 'repoa', path: 'src/a.ts', lang: 'typescript', start_line: 1, end_line: 20, score: 0.9, snippet: 'export const a = 1', chunk_id: '1', resource_link: 'kb://repoa/src/a.ts#L1-L20' }
          ]
          const response = { 
            hits: partialHits, 
            meta: { 
              top_k: top_k || 5, 
              model: 'text-embedding-3-small', 
              cursor: 'partial-cursor', 
              estimated_total: 10, 
              complete: false, 
              warnings: ['deadline_exceeded'] 
            } 
          }
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify(response))
          return
        }

        // Simulate embeddings unavailable
        if (body.embed_model === 'unavailable') {
          res.writeHead(503, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: { code: 'embeddings_unavailable', message: 'Embeddings service unavailable' } }))
          return
        }

        // Generate hits based on query
        const hits = query ? [
          { 
            repo: 'repoa', 
            path: 'src/a.ts', 
            lang: 'typescript', 
            start_line: 1, 
            end_line: 20, 
            score: 0.9, 
            snippet: 'export const a = 1', 
            chunk_id: '1', 
            resource_link: 'kb://repoa/src/a.ts#L1-L20' 
          },
          { 
            repo: 'repob', 
            path: 'src/b.py', 
            lang: 'python', 
            start_line: 5, 
            end_line: 15, 
            score: 0.8, 
            snippet: 'def test_function():\n    return True', 
            chunk_id: '2', 
            resource_link: 'kb://repob/src/b.py#L5-L15' 
          }
        ] : []

        // Simulate large snippet for truncation testing
        if (query === 'large-snippet') {
          hits[0].snippet = 'x'.repeat(600) // Exceeds 500-char cap
        }

        const response = { 
          hits, 
          meta: { 
            top_k: top_k || 5, 
            model: body.embed_model || 'text-embedding-3-small', 
            cursor: cursor || (hits.length ? 'opaque-cursor' : undefined), 
            estimated_total: hits.length, 
            complete: true, 
            warnings: top_k && top_k > 100 ? ['top_k clamped to 100'] : [] 
          } 
        }
        
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify(response))
        return
      }

      // GET /v1/health (optional)
      if (req.method === 'GET' && url.pathname === '/v1/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ status: 'healthy', version: '0.1.0' }))
        return
      }

      res.statusCode = 404
      res.end(JSON.stringify({ error: { code: 'not_found', message: 'not found' } }))
    } catch (e: any) {
      res.statusCode = 500
      res.end(JSON.stringify({ error: { code: 'mock_error', message: e?.message ?? String(e) } }))
    }
  })

  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      resolve(async () => {
        await new Promise(res => server.close(() => res(null)))
      })
    })
  })
}
