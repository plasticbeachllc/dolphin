import { describe, it, expect, beforeEach, afterEach, mock } from 'bun:test'
import { IndexQueue, type IndexProgress } from '../src/kb/index-queue'

// Global fetch mock
let fetchMock: any

beforeEach(() => {
  // Reset fetch mock before each test
  fetchMock = undefined
  globalThis.fetch = fetchMock
})

afterEach(() => {
  // Clean up any timers
})

describe('IndexQueue', () => {
  let queue: IndexQueue
  const KB_API_URL = 'http://localhost:7677'
  const REPO_NAME = 'test-repo'

  beforeEach(() => {
    queue = new IndexQueue(KB_API_URL, REPO_NAME)
  })

  afterEach(() => {
    queue.dispose()
  })

  describe('constructor', () => {
    it('should create queue with API URL and repo name', () => {
      const q = new IndexQueue('http://localhost:8080', 'my-repo')
      expect(q).toBeDefined()
      expect(q.getQueueDepth()).toBe(0)
    })

    it('should start with no active tasks', () => {
      expect(queue.getQueueDepth()).toBe(0)
      expect(queue.isIndexing()).toBe(false)
    })
  })

  describe('enqueueBatch', () => {
    it('should queue files for indexing', async () => {
      // Mock successful index request
      globalThis.fetch = mock(async (url: string, options?: any) => {
        return {
          ok: true,
          status: 200,
          json: async () => ({ task_id: 'task-123' })
        } as Response
      }) as any

      const files = ['src/file1.ts', 'src/file2.ts']
      const taskId = await queue.enqueueBatch(files)

      expect(taskId).toBe('task-123')
      expect(globalThis.fetch).toHaveBeenCalled()

      // Should track the task
      expect(queue.getQueueDepth()).toBe(1)
      expect(queue.isIndexing()).toBe(true)
    })

    it('should send correct request body', async () => {
      let capturedBody: any

      globalThis.fetch = mock(async (url: string, options?: any) => {
        capturedBody = JSON.parse(options.body)
        return {
          ok: true,
          status: 200,
          json: async () => ({ task_id: 'task-123' })
        } as Response
      }) as any

      const files = ['file1.ts', 'file2.ts', 'file3.ts']
      await queue.enqueueBatch(files)

      expect(capturedBody.repo).toBe(REPO_NAME)
      expect(capturedBody.files).toEqual(files)
      expect(capturedBody.incremental).toBe(true)
    })

    it('should send request to correct endpoint', async () => {
      let capturedUrl: string = ''

      globalThis.fetch = mock(async (url: string) => {
        capturedUrl = url
        return {
          ok: true,
          status: 200,
          json: async () => ({ task_id: 'task-123' })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      expect(capturedUrl).toBe(`${KB_API_URL}/v1/index`)
    })

    it('should handle API errors', async () => {
      globalThis.fetch = mock(async () => ({
        ok: false,
        status: 500,
        text: async () => 'Internal Server Error'
      })) as any

      await expect(queue.enqueueBatch(['test.ts'])).rejects.toThrow('Index queue failed')
    })

    it('should handle network errors', async () => {
      globalThis.fetch = mock(async () => {
        throw new Error('Network error')
      }) as any

      await expect(queue.enqueueBatch(['test.ts'])).rejects.toThrow('Network error')
    })

    it('should support empty file list', async () => {
      globalThis.fetch = mock(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-empty' })
      })) as any

      const taskId = await queue.enqueueBatch([])
      expect(taskId).toBe('task-empty')
    })

    it('should handle large file lists', async () => {
      globalThis.fetch = mock(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-large' })
      })) as any

      const largeFileList = Array.from({ length: 1000 }, (_, i) => `file${i}.ts`)
      const taskId = await queue.enqueueBatch(largeFileList)

      expect(taskId).toBe('task-large')
    })
  })

  describe('polling', () => {
    it('should start polling after enqueuing', async () => {
      let pollCount = 0

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        // Status endpoint
        pollCount++
        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: 'processing',
            progress: 50,
            total: 100,
            indexed: 50,
            skipped: 0
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Wait for polling to occur
      await new Promise(resolve => setTimeout(resolve, 2500))

      expect(pollCount).toBeGreaterThan(0)
    })

    it('should emit progress events', async () => {
      const progressEvents: number[] = []

      queue.on('progress', (progress: number) => {
        progressEvents.push(progress)
      })

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        // Return increasing progress
        const progress = Math.min(100, progressEvents.length * 25)
        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: progress === 100 ? 'completed' : 'processing',
            progress,
            total: 100,
            indexed: progress,
            skipped: 0
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Wait for polling
      await new Promise(resolve => setTimeout(resolve, 3000))

      expect(progressEvents.length).toBeGreaterThan(0)
    })

    it('should emit complete event when task finishes', async () => {
      let completeEvent: IndexProgress | null = null

      queue.on('complete', (status: IndexProgress) => {
        completeEvent = status
      })

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: 'completed',
            progress: 100,
            total: 100,
            indexed: 95,
            skipped: 5
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Wait for completion
      await new Promise(resolve => setTimeout(resolve, 2500))

      expect(completeEvent).not.toBeNull()
      expect(completeEvent?.status).toBe('completed')
      expect(completeEvent?.indexed).toBe(95)
      expect(completeEvent?.skipped).toBe(5)
    })

    it('should emit error event when task fails', async () => {
      let errorEvent: Error | null = null

      queue.on('error', (error: Error) => {
        errorEvent = error
      })

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: 'failed',
            progress: 50,
            total: 100,
            indexed: 45,
            skipped: 0,
            error: 'Indexing failed'
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Wait for error
      await new Promise(resolve => setTimeout(resolve, 2500))

      expect(errorEvent).not.toBeNull()
      expect(errorEvent?.message).toContain('Indexing failed')
    })

    it('should remove completed tasks from tracking', async () => {
      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: 'completed',
            progress: 100,
            total: 100,
            indexed: 100,
            skipped: 0
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      expect(queue.getQueueDepth()).toBe(1)

      // Wait for completion
      await new Promise(resolve => setTimeout(resolve, 2500))

      expect(queue.getQueueDepth()).toBe(0)
      expect(queue.isIndexing()).toBe(false)
    })

    it('should stop polling when no tasks remain', async () => {
      let pollCount = 0

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        pollCount++
        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: 'completed',
            progress: 100,
            total: 100,
            indexed: 100,
            skipped: 0
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Wait for completion
      await new Promise(resolve => setTimeout(resolve, 2500))

      const pollCountBefore = pollCount

      // Wait more - polling should have stopped
      await new Promise(resolve => setTimeout(resolve, 3000))

      expect(pollCount).toBe(pollCountBefore)
    })

    it('should handle status check errors gracefully', async () => {
      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        // Status check fails
        return {
          ok: false,
          status: 500
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Should not crash
      await new Promise(resolve => setTimeout(resolve, 2500))

      // Task should still be tracked
      expect(queue.getQueueDepth()).toBe(1)
    })
  })

  describe('getQueueDepth', () => {
    it('should return number of active tasks', async () => {
      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: `task-${Date.now()}` })
          } as Response
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: 'processing',
            progress: 50,
            total: 100,
            indexed: 50,
            skipped: 0
          })
        } as Response
      }) as any

      expect(queue.getQueueDepth()).toBe(0)

      await queue.enqueueBatch(['file1.ts'])
      expect(queue.getQueueDepth()).toBe(1)

      await queue.enqueueBatch(['file2.ts'])
      expect(queue.getQueueDepth()).toBe(2)
    })
  })

  describe('isIndexing', () => {
    it('should return true when tasks are active', async () => {
      globalThis.fetch = mock(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-123' })
      })) as any

      expect(queue.isIndexing()).toBe(false)

      await queue.enqueueBatch(['test.ts'])

      expect(queue.isIndexing()).toBe(true)
    })

    it('should return false when no tasks are active', () => {
      expect(queue.isIndexing()).toBe(false)
    })
  })

  describe('dispose', () => {
    it('should stop polling', async () => {
      let pollCount = 0

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        pollCount++
        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-123',
            status: 'processing',
            progress: 50,
            total: 100,
            indexed: 50,
            skipped: 0
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Wait for some polling
      await new Promise(resolve => setTimeout(resolve, 2500))

      const pollCountBefore = pollCount

      // Dispose
      queue.dispose()

      // Wait more - no more polling should occur
      await new Promise(resolve => setTimeout(resolve, 3000))

      expect(pollCount).toBe(pollCountBefore)
    })

    it('should clear active tasks', async () => {
      globalThis.fetch = mock(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ task_id: 'task-123' })
      })) as any

      await queue.enqueueBatch(['test.ts'])

      expect(queue.getQueueDepth()).toBe(1)

      queue.dispose()

      expect(queue.getQueueDepth()).toBe(0)
      expect(queue.isIndexing()).toBe(false)
    })

    it('should be safe to call multiple times', () => {
      queue.dispose()
      queue.dispose()
      queue.dispose()

      // Should not crash
      expect(queue.getQueueDepth()).toBe(0)
    })
  })

  describe('edge cases', () => {
    it('should handle multiple concurrent tasks', async () => {
      let taskCounter = 0

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          taskCounter++
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: `task-${taskCounter}` })
          } as Response
        }

        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: 'task-1',
            status: 'processing',
            progress: 50,
            total: 100,
            indexed: 50,
            skipped: 0
          })
        } as Response
      }) as any

      await Promise.all([
        queue.enqueueBatch(['file1.ts']),
        queue.enqueueBatch(['file2.ts']),
        queue.enqueueBatch(['file3.ts'])
      ])

      expect(queue.getQueueDepth()).toBe(3)
    })

    it('should handle task completion in non-sequential order', async () => {
      const taskStatuses = new Map([
        ['task-1', 'processing'],
        ['task-2', 'processing']
      ])

      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          const taskId = url.includes('task-1') ? 'task-1' : 'task-2'
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: taskId })
          } as Response
        }

        const taskId = url.split('/').pop()!
        const status = taskStatuses.get(taskId) || 'completed'

        return {
          ok: true,
          status: 200,
          json: async () => ({
            task_id: taskId,
            status,
            progress: status === 'completed' ? 100 : 50,
            total: 100,
            indexed: status === 'completed' ? 100 : 50,
            skipped: 0
          })
        } as Response
      }) as any

      await queue.enqueueBatch(['file1.ts'])
      await queue.enqueueBatch(['file2.ts'])

      expect(queue.getQueueDepth()).toBe(2)

      // Complete task-2 first
      taskStatuses.set('task-2', 'completed')

      await new Promise(resolve => setTimeout(resolve, 2500))

      // Complete task-1
      taskStatuses.set('task-1', 'completed')

      await new Promise(resolve => setTimeout(resolve, 2500))

      expect(queue.getQueueDepth()).toBe(0)
    })

    it('should handle malformed status responses', async () => {
      globalThis.fetch = mock(async (url: string) => {
        if (url.includes('/index')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ task_id: 'task-123' })
          } as Response
        }

        // Malformed response
        return {
          ok: true,
          status: 200,
          json: async () => null
        } as Response
      }) as any

      await queue.enqueueBatch(['test.ts'])

      // Should not crash
      await new Promise(resolve => setTimeout(resolve, 2500))
    })
  })
})
