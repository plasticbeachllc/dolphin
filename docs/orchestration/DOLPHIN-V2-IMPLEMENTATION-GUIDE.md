# Dolphin v2 Orchestration - Implementation Guide

**Document Version:** 1.0  
**Date:** 2025-11-10  
**Purpose:** Detailed week-by-week implementation roadmap with daily tasks

---

## How to Use This Guide

This document provides a concrete, day-by-day breakdown of the v2 implementation. Each day includes:
- **Objective:** What you're trying to achieve
- **Tasks:** Specific implementation steps
- **Deliverables:** What should be done by end of day
- **Tests:** What tests should pass
- **Checkpoint:** How to verify progress

**Daily Workflow:**
1. Review objectives and tasks for the day
2. Implement features with tests first (TDD)
3. Verify deliverables are complete
4. Run checkpoint verification
5. Commit and push changes
6. Plan next day

---

## Phase 1: Foundation (Weeks 1-3)

### Week 1: Core Architecture

#### Day 1: Project Setup & Architecture Scaffolding

**Objective:** Set up project structure and define core interfaces

**Tasks:**
1. Create directory structure:
```bash
agent-core-v2/
├── src/
│   ├── orchestrator/
│   │   ├── orchestrator.ts
│   │   └── state-machine.ts
│   ├── workflows/
│   │   ├── editor-workflow.ts
│   │   └── architect-workflow.ts
│   ├── claude/
│   │   ├── provider.ts
│   │   ├── auth.ts
│   │   └── stream-parser.ts
│   ├── context/
│   │   ├── builder.ts
│   │   └── kb-client.ts
│   ├── state/
│   │   ├── store.ts
│   │   └── serializer.ts
│   ├── prompts/
│   │   └── builder.ts
│   ├── types/
│   │   ├── index.ts
│   │   ├── workflow.ts
│   │   └── session.ts
│   └── main.ts
├── tests/
│   ├── orchestrator/
│   ├── workflows/
│   ├── claude/
│   ├── context/
│   └── state/
├── package.json
├── tsconfig.json
├── vitest.config.ts
└── README.md
```

2. Initialize project:
```bash
cd agent-core-v2
bun init
bun add zod toml
bun add -d @types/node vitest @vitest/coverage-v8 typescript
```

3. Define core types in `src/types/index.ts`:
```typescript
export type WorkflowMode = 'editor' | 'architect'

export type WorkflowState = 
  | 'idle'
  | 'researching'
  | 'planning'
  | 'awaiting_approval'
  | 'plan_revision'
  | 'executing'
  | 'validating'
  | 'complete'
  | 'cancelled'
  | 'error'

export interface TaskInput {
  mode: WorkflowMode
  message: string
  context: ContextHints
  conversationHistory?: Message[]
}

export interface ContextHints {
  files: string[]
  folders: string[]
  selection: string
}

export interface TaskSession {
  id: string
  conversationId: string
  mode: WorkflowMode
  state: WorkflowState
  createdAt: Date
  updatedAt: Date
  input: TaskInput
  research?: ResearchResult
  plan?: Plan
  execution?: ExecutionResult
  metadata: SessionMetadata
}

export interface Plan {
  version: number
  status: 'pending_approval' | 'approved' | 'rejected' | 'cancelled'
  createdAt: Date
  approvedAt?: Date
  rejectedAt?: Date
  content: string
  contentPath: string
  overview: string
  filesToModify: string[]
  filesToCreate: string[]
  complexity: 'low' | 'medium' | 'high'
  estimatedTokens: number
  estimatedCost: number
  revisions: PlanRevision[]
}

export interface SessionMetadata {
  totalTokens: number
  totalCost: number
  modelsUsed: string[]
}

// ... (add remaining types)
```

4. Set up testing framework in `vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: ['tests/**', '**/*.test.ts']
    }
  }
})
```

**Deliverables:**
- ✅ Complete directory structure
- ✅ All core types defined
- ✅ Testing framework configured
- ✅ README with architecture overview
- ✅ Initial commit pushed

**Tests:** None yet (setup day)

**Checkpoint:**
```bash
# Verify structure
tree src/
# Verify types compile
bun run tsc --noEmit
# Verify tests run (even if empty)
bun test
```

---

#### Day 2: Orchestrator Skeleton

**Objective:** Implement core Orchestrator class with state machine

**Tasks:**
1. Implement state machine in `src/orchestrator/state-machine.ts`:
```typescript
export class WorkflowStateMachine {
  private state: WorkflowState = 'idle'
  private transitions: Map<WorkflowState, WorkflowState[]>
  
  constructor() {
    this.transitions = new Map([
      ['idle', ['researching', 'executing']],
      ['researching', ['planning', 'error', 'cancelled']],
      ['planning', ['awaiting_approval', 'error', 'cancelled']],
      ['awaiting_approval', ['plan_revision', 'executing', 'cancelled']],
      ['plan_revision', ['planning', 'cancelled']],
      ['executing', ['validating', 'complete', 'error', 'cancelled']],
      ['validating', ['complete', 'error']],
      ['complete', []],
      ['cancelled', []],
      ['error', []]
    ])
  }
  
  transition(to: WorkflowState): void {
    const validTransitions = this.transitions.get(this.state) || []
    if (!validTransitions.includes(to)) {
      throw new Error(`Invalid transition from ${this.state} to ${to}`)
    }
    this.state = to
  }
  
  canTransitionTo(to: WorkflowState): boolean {
    return (this.transitions.get(this.state) || []).includes(to)
  }
  
  getCurrentState(): WorkflowState {
    return this.state
  }
}
```

2. Implement Orchestrator in `src/orchestrator/orchestrator.ts`:
```typescript
export class Orchestrator {
  private sessions: Map<string, TaskSession> = new Map()
  private stateStore: StateStore
  private editorWorkflow: EditorWorkflow
  private architectWorkflow: ArchitectWorkflow
  
  constructor(deps: OrchestratorDeps) {
    this.stateStore = deps.stateStore
    this.editorWorkflow = deps.editorWorkflow
    this.architectWorkflow = deps.architectWorkflow
  }
  
  async startTask(input: TaskInput): Promise<TaskSession> {
    const session = this.createSession(input)
    this.sessions.set(session.id, session)
    
    // Route to appropriate workflow
    const workflow = input.mode === 'editor' 
      ? this.editorWorkflow 
      : this.architectWorkflow
    
    // Start workflow execution (async)
    this.executeWorkflow(session, workflow)
    
    return session
  }
  
  async getSession(sessionId: string): Promise<TaskSession | null> {
    // Check in-memory first
    const session = this.sessions.get(sessionId)
    if (session) return session
    
    // Load from disk
    return await this.stateStore.loadSession(sessionId)
  }
  
  async approveTask(sessionId: string): Promise<void> {
    const session = await this.getSession(sessionId)
    if (!session) throw new Error('Session not found')
    
    if (session.state !== 'awaiting_approval') {
      throw new Error('Session not awaiting approval')
    }
    
    // Update plan status
    if (session.plan) {
      session.plan.status = 'approved'
      session.plan.approvedAt = new Date()
    }
    
    // Continue to execution
    await this.stateStore.saveSession(session)
    // Trigger implementation phase
  }
  
  async rejectTask(sessionId: string, reason?: string): Promise<void> {
    const session = await this.getSession(sessionId)
    if (!session) throw new Error('Session not found')
    
    if (session.plan) {
      session.plan.status = 'rejected'
      session.plan.rejectedAt = new Date()
    }
    
    session.state = 'cancelled'
    await this.stateStore.saveSession(session)
  }
  
  async revisePlan(sessionId: string, feedback: string): Promise<void> {
    const session = await this.getSession(sessionId)
    if (!session) throw new Error('Session not found')
    
    session.state = 'plan_revision'
    await this.stateStore.saveSession(session)
    
    // Trigger plan revision in architect workflow
  }
  
  private createSession(input: TaskInput): TaskSession {
    return {
      id: `sess_${generateId()}`,
      conversationId: `conv_${generateId()}`,
      mode: input.mode,
      state: 'idle',
      createdAt: new Date(),
      updatedAt: new Date(),
      input,
      metadata: {
        totalTokens: 0,
        totalCost: 0,
        modelsUsed: []
      }
    }
  }
  
  private async executeWorkflow(
    session: TaskSession,
    workflow: Workflow
  ): Promise<void> {
    try {
      const updates = workflow.execute(session.input)
      
      for await (const update of updates) {
        await this.handleWorkflowUpdate(session, update)
      }
    } catch (error) {
      session.state = 'error'
      await this.stateStore.saveSession(session)
    }
  }
  
  private async handleWorkflowUpdate(
    session: TaskSession,
    update: WorkflowUpdate
  ): Promise<void> {
    if (update.type === 'state_change') {
      session.state = update.data.state
      session.updatedAt = new Date()
      await this.stateStore.saveSession(session)
    }
    // Handle other update types
  }
}
```

3. Write tests in `tests/orchestrator/orchestrator.test.ts`:
```typescript
describe('Orchestrator', () => {
  let orchestrator: Orchestrator
  let mockStateStore: StateStore
  let mockEditorWorkflow: EditorWorkflow
  let mockArchitectWorkflow: ArchitectWorkflow
  
  beforeEach(() => {
    mockStateStore = createMockStateStore()
    mockEditorWorkflow = createMockWorkflow('editor')
    mockArchitectWorkflow = createMockWorkflow('architect')
    
    orchestrator = new Orchestrator({
      stateStore: mockStateStore,
      editorWorkflow: mockEditorWorkflow,
      architectWorkflow: mockArchitectWorkflow
    })
  })
  
  describe('startTask', () => {
    it('should create session for editor mode', async () => {
      const input: TaskInput = {
        mode: 'editor',
        message: 'Fix the bug',
        context: { files: [], folders: [], selection: '' }
      }
      
      const session = await orchestrator.startTask(input)
      
      expect(session.id).toMatch(/^sess_/)
      expect(session.mode).toBe('editor')
      expect(session.state).toBe('idle')
    })
    
    it('should create session for architect mode', async () => {
      const input: TaskInput = {
        mode: 'architect',
        message: 'Add authentication',
        context: { files: [], folders: [], selection: '' }
      }
      
      const session = await orchestrator.startTask(input)
      
      expect(session.mode).toBe('architect')
    })
    
    it('should route to correct workflow', async () => {
      const input: TaskInput = {
        mode: 'editor',
        message: 'Test',
        context: { files: [], folders: [], selection: '' }
      }
      
      await orchestrator.startTask(input)
      
      expect(mockEditorWorkflow.execute).toHaveBeenCalled()
      expect(mockArchitectWorkflow.execute).not.toHaveBeenCalled()
    })
  })
  
  describe('approveTask', () => {
    it('should approve plan and transition to execution', async () => {
      const session = await createTestSession({
        state: 'awaiting_approval',
        plan: { status: 'pending_approval' }
      })
      mockStateStore.loadSession.mockResolvedValue(session)
      
      await orchestrator.approveTask(session.id)
      
      expect(session.plan?.status).toBe('approved')
      expect(session.plan?.approvedAt).toBeDefined()
    })
    
    it('should throw if session not awaiting approval', async () => {
      const session = await createTestSession({ state: 'executing' })
      mockStateStore.loadSession.mockResolvedValue(session)
      
      await expect(orchestrator.approveTask(session.id))
        .rejects.toThrow('not awaiting approval')
    })
  })
  
  // ... more tests
})
```

**Deliverables:**
- ✅ WorkflowStateMachine implemented
- ✅ Orchestrator class with core methods
- ✅ 15+ unit tests passing
- ✅ State transitions validated

**Tests to Pass:**
```bash
bun test tests/orchestrator/
# Should see: 15+ tests passing
```

**Checkpoint:**
```bash
# Verify compilation
bun run tsc --noEmit
# Verify tests
bun test tests/orchestrator/ --coverage
# Coverage should be >80% for orchestrator files
```

---

#### Day 3: StateStore with TOML Persistence

**Objective:** Implement TOML-based state persistence

**Tasks:**
1. Implement TOML serializer in `src/state/serializer.ts`:
```typescript
import TOML from '@iarna/toml'

export class TOMLSerializer {
  serialize(session: TaskSession): string {
    const obj = this.sessionToObject(session)
    return TOML.stringify(obj)
  }
  
  deserialize(toml: string): TaskSession {
    const obj = TOML.parse(toml)
    return this.objectToSession(obj)
  }
  
  private sessionToObject(session: TaskSession): any {
    return {
      session: {
        id: session.id,
        conversation_id: session.conversationId,
        mode: session.mode,
        state: session.state,
        created_at: session.createdAt.toISOString(),
        updated_at: session.updatedAt.toISOString()
      },
      input: {
        message: session.input.message,
        context: {
          files: session.input.context.files,
          folders: session.input.context.folders,
          selection: session.input.context.selection
        }
      },
      research: session.research ? {
        completed_at: session.research.completedAt.toISOString(),
        model: session.research.model,
        tokens_used: session.research.tokensUsed,
        findings: session.research.findings,
        kb_searches: session.research.kbSearches
      } : undefined,
      plan: session.plan ? {
        version: session.plan.version,
        status: session.plan.status,
        created_at: session.plan.createdAt.toISOString(),
        approved_at: session.plan.approvedAt?.toISOString(),
        content_path: session.plan.contentPath,
        overview: session.plan.overview,
        files_to_modify: session.plan.filesToModify,
        complexity: session.plan.complexity,
        estimated_tokens: session.plan.estimatedTokens,
        estimated_cost: session.plan.estimatedCost,
        revisions: session.plan.revisions.map(r => ({
          version: r.version,
          created_at: r.createdAt.toISOString(),
          rejected_at: r.rejectedAt?.toISOString(),
          rejected_reason: r.rejectedReason,
          content_path: r.contentPath
        }))
      } : undefined,
      metadata: session.metadata
    }
  }
  
  private objectToSession(obj: any): TaskSession {
    // Reverse transformation
    // ... implementation
  }
}
```

2. Implement StateStore in `src/state/store.ts`:
```typescript
export class StateStore {
  private storagePath: string
  private serializer: TOMLSerializer
  
  constructor(config: StateStoreConfig) {
    this.storagePath = config.storagePath || '.dolphin'
    this.serializer = new TOMLSerializer()
    this.ensureDirectories()
  }
  
  async saveSession(session: TaskSession): Promise<void> {
    const sessionPath = this.getSessionPath(session.id)
    const toml = this.serializer.serialize(session)
    
    // Atomic write using temp file
    const tempPath = `${sessionPath}.tmp`
    await writeFile(tempPath, toml, 'utf-8')
    await rename(tempPath, sessionPath)
  }
  
  async loadSession(sessionId: string): Promise<TaskSession | null> {
    const sessionPath = this.getSessionPath(sessionId)
    
    if (!existsSync(sessionPath)) {
      return null
    }
    
    const toml = await readFile(sessionPath, 'utf-8')
    return this.serializer.deserialize(toml)
  }
  
  async savePlan(sessionId: string, plan: Plan): Promise<void> {
    // Save plan content as markdown
    const planPath = this.getPlanPath(sessionId, plan.version)
    await writeFile(planPath, plan.content, 'utf-8')
    
    // Update session with plan metadata
    const session = await this.loadSession(sessionId)
    if (session) {
      session.plan = {
        ...plan,
        contentPath: planPath
      }
      await this.saveSession(session)
    }
  }
  
  async loadPlan(sessionId: string, version?: number): Promise<Plan | null> {
    const session = await this.loadSession(sessionId)
    if (!session?.plan) return null
    
    const planVersion = version || session.plan.version
    const planPath = this.getPlanPath(sessionId, planVersion)
    
    if (!existsSync(planPath)) return null
    
    const content = await readFile(planPath, 'utf-8')
    return {
      ...session.plan,
      content
    }
  }
  
  async listSessions(): Promise<SessionSummary[]> {
    const sessionsDir = join(this.storagePath, 'sessions')
    const files = await readdir(sessionsDir)
    
    const summaries = await Promise.all(
      files
        .filter(f => f.endsWith('.toml'))
        .map(async f => {
          const sessionId = f.replace('.toml', '')
          const session = await this.loadSession(sessionId)
          return this.toSummary(session)
        })
    )
    
    return summaries.sort((a, b) => 
      b.updatedAt.getTime() - a.updatedAt.getTime()
    )
  }
  
  async deleteSession(sessionId: string): Promise<void> {
    const sessionPath = this.getSessionPath(sessionId)
    await unlink(sessionPath)
    
    // Delete associated plans
    const plansDir = join(this.storagePath, 'plans')
    const planFiles = await readdir(plansDir)
    const sessionPlans = planFiles.filter(f => 
      f.startsWith(`plan_${sessionId}_`)
    )
    
    await Promise.all(
      sessionPlans.map(f => unlink(join(plansDir, f)))
    )
  }
  
  private ensureDirectories(): void {
    const dirs = [
      this.storagePath,
      join(this.storagePath, 'sessions'),
      join(this.storagePath, 'plans'),
      join(this.storagePath, 'conversations')
    ]
    
    for (const dir of dirs) {
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true })
      }
    }
  }
  
  private getSessionPath(sessionId: string): string {
    return join(this.storagePath, 'sessions', `${sessionId}.toml`)
  }
  
  private getPlanPath(sessionId: string, version: number): string {
    return join(
      this.storagePath,
      'plans',
      `plan_${sessionId}_v${version}.md`
    )
  }
}
```

3. Write tests in `tests/state/store.test.ts`:
```typescript
describe('StateStore', () => {
  let stateStore: StateStore
  let tempDir: string
  
  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'dolphin-test-'))
    stateStore = new StateStore({ storagePath: tempDir })
  })
  
  afterEach(() => {
    rmSync(tempDir, { recursive: true, force: true })
  })
  
  describe('saveSession', () => {
    it('should save session as TOML', async () => {
      const session = createTestSession()
      
      await stateStore.saveSession(session)
      
      const sessionPath = join(tempDir, 'sessions', `${session.id}.toml`)
      expect(existsSync(sessionPath)).toBe(true)
      
      const content = await readFile(sessionPath, 'utf-8')
      expect(content).toContain('[session]')
      expect(content).toContain(`id = "${session.id}"`)
    })
    
    it('should use atomic writes', async () => {
      const session = createTestSession()
      
      // Simulate concurrent writes
      await Promise.all([
        stateStore.saveSession(session),
        stateStore.saveSession({ ...session, state: 'executing' })
      ])
      
      const loaded = await stateStore.loadSession(session.id)
      expect(loaded?.state).toBeOneOf(['idle', 'executing'])
      // Should not be corrupted
    })
  })
  
  describe('loadSession', () => {
    it('should load saved session', async () => {
      const session = createTestSession()
      await stateStore.saveSession(session)
      
      const loaded = await stateStore.loadSession(session.id)
      
      expect(loaded?.id).toBe(session.id)
      expect(loaded?.mode).toBe(session.mode)
      expect(loaded?.state).toBe(session.state)
    })
    
    it('should return null for non-existent session', async () => {
      const loaded = await stateStore.loadSession('nonexistent')
      expect(loaded).toBeNull()
    })
  })
  
  describe('savePlan', () => {
    it('should save plan content as markdown', async () => {
      const session = createTestSession()
      await stateStore.saveSession(session)
      
      const plan: Plan = {
        version: 1,
        status: 'pending_approval',
        createdAt: new Date(),
        content: '# Implementation Plan\n\nThis is the plan...',
        contentPath: '',
        overview: 'Add authentication',
        filesToModify: ['app.py'],
        filesToCreate: ['auth.py'],
        complexity: 'medium',
        estimatedTokens: 5000,
        estimatedCost: 0.15,
        revisions: []
      }
      
      await stateStore.savePlan(session.id, plan)
      
      const planPath = join(tempDir, 'plans', `plan_${session.id}_v1.md`)
      expect(existsSync(planPath)).toBe(true)
      
      const content = await readFile(planPath, 'utf-8')
      expect(content).toBe(plan.content)
    })
  })
  
  // ... more tests
})
```

**Deliverables:**
- ✅ TOMLSerializer with bidirectional conversion
- ✅ StateStore with CRUD operations
- ✅ Atomic writes for data safety
- ✅ 20+ unit tests passing
- ✅ Directory structure auto-created

**Tests to Pass:**
```bash
bun test tests/state/
# Should see: 20+ tests passing
```

**Checkpoint:**
```bash
# Test round-trip serialization
bun test tests/state/serializer.test.ts
# Test persistence
bun test tests/state/store.test.ts
# Check coverage
bun test tests/state/ --coverage
```

---

#### Day 4: JSON-RPC Message Handlers

**Objective:** Implement JSON-RPC communication layer for VSCode integration

**Tasks:**
1. Implement message framing in `src/ipc/message-framing.ts`:
```typescript
export class MessageFraming {
  private buffer = ''
  
  async write(message: RPCMessage, writer: WritableStream): Promise<void> {
    const json = JSON.stringify(message)
    const buffer = Buffer.from(json, 'utf-8')
    const header = `Content-Length: ${buffer.length}\r\n\r\n`
    
    const data = Buffer.from(header + json, 'utf-8')
    await writer.write(data)
  }
  
  async *read(reader: ReadableStream): AsyncIterator<RPCMessage> {
    const decoder = new TextDecoder()
    
    for await (const chunk of reader) {
      this.buffer += decoder.decode(chunk, { stream: true })
      
      while (true) {
        const match = this.buffer.match(/Content-Length: (\d+)\r\n\r\n/)
        if (!match) break
        
        const length = parseInt(match[1])
        const start = match[0].length
        
        if (this.buffer.length < start + length) break
        
        const json = this.buffer.slice(start, start + length)
        this.buffer = this.buffer.slice(start + length)
        
        yield JSON.parse(json) as RPCMessage
      }
    }
  }
}
```

2. Implement RPC handler in `src/ipc/rpc-handler.ts`:
```typescript
export class RPCHandler {
  private methods: Map<string, RPCMethod> = new Map()
  private framing: MessageFraming
  
  constructor() {
    this.framing = new MessageFraming()
  }
  
  registerMethod(name: string, handler: RPCMethod): void {
    this.methods.set(name, handler)
  }
  
  async handleMessage(
    message: RPCRequest,
    writer: WritableStream
  ): Promise<void> {
    try {
      const method = this.methods.get(message.method)
      
      if (!method) {
        await this.sendError(message.id, {
          code: 'METHOD_NOT_FOUND',
          message: `Method not found: ${message.method}`
        }, writer)
        return
      }
      
      const result = await method(message.params)
      
      await this.sendResponse(message.id, result, writer)
    } catch (error) {
      await this.sendError(message.id, {
        code: 'INTERNAL_ERROR',
        message: error.message,
        data: error
      }, writer)
    }
  }
  
  async sendResponse(
    id: string,
    result: unknown,
    writer: WritableStream
  ): Promise<void> {
    const response: RPCResponse = {
      jsonrpc: '2.0',
      id,
      result
    }
    
    await this.framing.write(response, writer)
  }
  
  async sendNotification(
    method: string,
    params: unknown,
    writer: WritableStream
  ): Promise<void> {
    const notification: RPCNotification = {
      jsonrpc: '2.0',
      method,
      params
    }
    
    await this.framing.write(notification, writer)
  }
  
  private async sendError(
    id: string,
    error: RPCError,
    writer: WritableStream
  ): Promise<void> {
    const response: RPCErrorResponse = {
      jsonrpc: '2.0',
      id,
      error
    }
    
    await this.framing.write(response, writer)
  }
}
```

3. Implement main entry point in `src/main.ts`:
```typescript
export class AgentCoreV2 {
  private orchestrator: Orchestrator
  private rpcHandler: RPCHandler
  
  constructor(deps: AgentCoreDeps) {
    this.orchestrator = deps.orchestrator
    this.rpcHandler = new RPCHandler()
    this.registerMethods()
  }
  
  async start(): Promise<void> {
    const stdin = process.stdin
    const stdout = process.stdout
    
    // Set up message handling
    const messageStream = this.rpcHandler.framing.read(stdin)
    
    for await (const message of messageStream) {
      if ('method' in message && 'id' in message) {
        // Request
        await this.rpcHandler.handleMessage(message, stdout)
      } else if ('method' in message) {
        // Notification (from extension)
        // Handle notification
      }
    }
  }
  
  private registerMethods(): void {
    this.rpcHandler.registerMethod('task.start', async (params) => {
      return await this.orchestrator.startTask(params as TaskInput)
    })
    
    this.rpcHandler.registerMethod('task.status', async (params) => {
      const { sessionId } = params as { sessionId: string }
      return await this.orchestrator.getSession(sessionId)
    })
    
    this.rpcHandler.registerMethod('task.approve', async (params) => {
      const { sessionId } = params as { sessionId: string }
      await this.orchestrator.approveTask(sessionId)
      return { success: true }
    })
    
    this.rpcHandler.registerMethod('task.reject', async (params) => {
      const { sessionId, reason } = params as { 
        sessionId: string
        reason?: string 
      }
      await this.orchestrator.rejectTask(sessionId, reason)
      return { success: true }
    })
    
    this.rpcHandler.registerMethod('task.revise', async (params) => {
      const { sessionId, feedback } = params as {
        sessionId: string
        feedback: string
      }
      await this.orchestrator.revisePlan(sessionId, feedback)
      return { success: true }
    })
    
    this.rpcHandler.registerMethod('task.cancel', async (params) => {
      const { sessionId } = params as { sessionId: string }
      await this.orchestrator.cancelTask(sessionId)
      return { success: true }
    })
  }
}

// Entry point
async function main() {
  const stateStore = new StateStore({ storagePath: '.dolphin' })
  const claudeProvider = new ClaudeProvider({ /* config */ })
  const kbClient = new KBClient({ /* config */ })
  const contextBuilder = new ContextBuilder({ kbClient })
  
  const editorWorkflow = new EditorWorkflow({
    claudeProvider,
    contextBuilder
  })
  
  const architectWorkflow = new ArchitectWorkflow({
    claudeProvider,
    contextBuilder
  })
  
  const orchestrator = new Orchestrator({
    stateStore,
    editorWorkflow,
    architectWorkflow
  })
  
  const agentCore = new AgentCoreV2({ orchestrator })
  
  await agentCore.start()
}

main().catch(console.error)
```

4. Write tests in `tests/ipc/rpc-handler.test.ts`:
```typescript
describe('RPCHandler', () => {
  let rpcHandler: RPCHandler
  let mockWriter: MockWritableStream
  
  beforeEach(() => {
    rpcHandler = new RPCHandler()
    mockWriter = new MockWritableStream()
  })
  
  describe('method registration', () => {
    it('should register and call methods', async () => {
      const mockMethod = vi.fn().mockResolvedValue({ result: 'test' })
      rpcHandler.registerMethod('test.method', mockMethod)
      
      const request: RPCRequest = {
        jsonrpc: '2.0',
        id: 'req-1',
        method: 'test.method',
        params: { arg: 'value' }
      }
      
      await rpcHandler.handleMessage(request, mockWriter)
      
      expect(mockMethod).toHaveBeenCalledWith({ arg: 'value' })
    })
    
    it('should return error for unknown method', async () => {
      const request: RPCRequest = {
        jsonrpc: '2.0',
        id: 'req-1',
        method: 'unknown.method',
        params: {}
      }
      
      await rpcHandler.handleMessage(request, mockWriter)
      
      const response = mockWriter.getLastMessage()
      expect(response.error).toBeDefined()
      expect(response.error.code).toBe('METHOD_NOT_FOUND')
    })
  })
  
  describe('error handling', () => {
    it('should catch and return errors', async () => {
      const mockMethod = vi.fn().mockRejectedValue(
        new Error('Test error')
      )
      rpcHandler.registerMethod('test.error', mockMethod)
      
      const request: RPCRequest = {
        jsonrpc: '2.0',
        id: 'req-1',
        method: 'test.error',
        params: {}
      }
      
      await rpcHandler.handleMessage(request, mockWriter)
      
      const response = mockWriter.getLastMessage()
      expect(response.error).toBeDefined()
      expect(response.error.message).toBe('Test error')
    })
  })
})
```

**Deliverables:**
- ✅ Message framing with Content-Length headers
- ✅ RPCHandler with method registration
- ✅ Main entry point with method handlers
- ✅ 15+ unit tests passing
- ✅ End-to-end message flow tested

**Tests to Pass:**
```bash
bun test tests/ipc/
# Should see: 15+ tests passing
```

**Checkpoint:**
```bash
# Test message framing
echo '{"jsonrpc":"2.0","id":"1","method":"test","params":{}}' | bun run src/main.ts
# Should not crash, should respond with error (method not found)

# Test with real orchestrator
bun run src/main.ts
# Send JSON-RPC request via stdin
# Verify response on stdout
```

---

#### Day 5: Review, Integration, and Week Planning

**Objective:** Integrate week's work, comprehensive testing, plan Week 2

**Tasks:**
1. Integration testing:
   - Test Orchestrator + StateStore integration
   - Test RPC + Orchestrator integration
   - Test full message flow end-to-end

2. Code review and refactoring:
   - Review all code from the week
   - Refactor for clarity and maintainability
   - Add missing documentation
   - Fix any bugs found

3. Documentation:
   - Update README with Week 1 progress
   - Document APIs and interfaces
   - Add code examples
   - Create troubleshooting guide

4. Week 2 planning:
   - Review Day 1-5 tasks for Week 2
   - Identify dependencies
   - Set up tracking
   - Prepare environment

**Deliverables:**
- ✅ All Week 1 tests passing (50+)
- ✅ Integration tests written and passing
- ✅ Documentation updated
- ✅ Week 2 tasks prioritized
- ✅ Clean commit history

**Tests to Pass:**
```bash
# All unit tests
bun test
# Should see: 50+ tests passing

# Coverage report
bun test --coverage
# Should see: >80% coverage for Week 1 files
```

**Checkpoint:**
```bash
# Verify entire system compiles
bun run tsc --noEmit

# Verify all tests pass
bun test

# Verify main entry point works
bun run src/main.ts < test-input.json

# Check git status
git status
# Should be clean after committing Week 1 work
```

---

### Week 2: Claude Provider & Editor Workflow

*(Continue with Days 6-10...)*

---

### Week 3: Context Management & KB Integration

*(Continue with Days 11-15...)*

---

## Phase 2: Architect Workflow (Weeks 4-6)

### Week 4: Research & Planning Phases

*(Continue with Days 16-20...)*

---

### Week 5: User Approval Flow

*(Continue with Days 21-25...)*

---

### Week 6: Implementation & Validation

*(Continue with Days 26-30...)*

---

## Phase 3: Polish & Optimization (Weeks 7-9)

### Week 7: UX Refinement

*(Continue with Days 31-35...)*

---

### Week 8: Observability Integration

*(Continue with Days 36-40...)*

---

### Week 9: Comprehensive Testing & Documentation

*(Continue with Days 41-45...)*

---

## Daily Checklist Template

Use this template for each day:

```markdown
## Day X: [Title]

### Morning (9:00 AM - 12:00 PM)
- [ ] Review objectives and tasks
- [ ] Set up environment
- [ ] Write tests first (TDD)
- [ ] Implement feature 1

### Afternoon (1:00 PM - 5:00 PM)
- [ ] Implement feature 2
- [ ] Implement feature 3
- [ ] Run all tests
- [ ] Code review

### Evening (5:00 PM - 6:00 PM)
- [ ] Verify deliverables complete
- [ ] Run checkpoint verification
- [ ] Update documentation
- [ ] Commit and push changes
- [ ] Plan next day

### Blockers/Questions
- List any blockers or questions here

### Notes
- Any important notes or learnings
```

---

## Progress Tracking

### Weekly Status Template

```markdown
# Week X Status Report

## Completed
- [ ] Day 1: [Title] ✅
- [ ] Day 2: [Title] ✅
- [ ] Day 3: [Title] ✅
- [ ] Day 4: [Title] ✅
- [ ] Day 5: [Title] ✅

## Metrics
- Tests passing: X / Y
- Code coverage: X%
- Issues resolved: X
- PRs merged: X

## Risks/Blockers
- List any risks or blockers

## Next Week Plan
- Preview of Week X+1 objectives
```

---

## Conclusion

This implementation guide provides a concrete, day-by-day roadmap for building Dolphin v2. Each day has clear objectives, tasks, deliverables, and checkpoints to verify progress.

**Key Principles:**
1. Test-driven development (write tests first)
2. Small, incremental progress
3. Daily checkpoints
4. Weekly reviews and planning
5. Clear deliverables and acceptance criteria

**Next Steps:**
1. Review this guide
2. Set up tracking system (GitHub project, Jira, etc.)
3. Begin Day 1 when ready
4. Follow the daily workflow
5. Adapt as needed based on learnings

**Remember:** This is a guide, not a rigid plan. Adjust as you learn and encounter new information. The goal is steady, sustainable progress toward a high-quality v2 implementation.

---

**Document Version:** 1.0  
**Date:** 2025-11-10  
**Status:** Ready for Implementation
