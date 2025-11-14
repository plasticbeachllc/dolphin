/**
 * Orchestrator - Core State Machine for Dolphin v2
 *
 * Central coordinator that manages workflow state, routes between modes,
 * and handles user interactions.
 *
 * Based on: docs/orchestration/DOLPHIN-V2-ORCHESTRATION-PROJECT-PLAN.md
 */

import { EventEmitter } from "events";
import { randomBytes } from "crypto";
import type {
  IOrchestrator,
  TaskInput,
  TaskSession,
  WorkflowPhase,
  WorkflowUpdate,
  WorkflowState,
  IWorkflow,
} from "../types/index.js";

/**
 * Configuration for the orchestrator
 */
export interface OrchestratorConfig {
  workspaceRoot: string;
  stateStore: any; // Will be properly typed when StateStore is implemented
  editorWorkflow: IWorkflow;
  architectWorkflow: IWorkflow;
}

/**
 * Internal session state tracking
 */
interface InternalSession extends TaskSession {
  eventEmitter: EventEmitter;
  workflowIterator?: AsyncIterableIterator<WorkflowUpdate>;
  approvalResolver?: (approved: boolean) => void;
  revisionResolver?: (revised: boolean) => void;
}

/**
 * Orchestrator manages workflow execution, state transitions, and user interactions
 */
export class Orchestrator implements IOrchestrator {
  private sessions: Map<string, InternalSession> = new Map();
  private config: OrchestratorConfig;

  constructor(config: OrchestratorConfig) {
    this.config = config;
  }

  /**
   * Start a new task session
   */
  async startTask(input: TaskInput): Promise<TaskSession> {
    // Generate session ID
    const sessionId = this.generateSessionId();

    // Create initial session
    const session: InternalSession = {
      id: sessionId,
      mode: input.mode,
      state: "idle",
      metadata: {
        tokensUsed: 0,
        estimatedCost: 0,
        startedAt: new Date().toISOString(),
      },
      input,
      eventEmitter: new EventEmitter(),
    };

    // Store session
    this.sessions.set(sessionId, session);

    // Persist to state store
    await this.config.stateStore.saveSession(this.toPublicSession(session));

    // Start workflow execution asynchronously
    this.executeWorkflow(session).catch((error) => {
      console.error(`[Orchestrator] Workflow execution failed for ${sessionId}:`, error);
      this.transitionState(session, "error");
    });

    return this.toPublicSession(session);
  }

  /**
   * Approve a pending plan
   */
  async approveTask(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId);

    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    if (session.state !== "awaiting_approval") {
      throw new Error(
        `Session ${sessionId} is not awaiting approval (current state: ${session.state})`
      );
    }

    // Update plan status
    if (session.plan) {
      session.plan.status = "approved";
      session.plan.approvedAt = new Date().toISOString();
    }

    // Resolve the approval promise to continue workflow
    if (session.approvalResolver) {
      session.approvalResolver(true);
      session.approvalResolver = undefined;
    }

    // Persist
    await this.config.stateStore.saveSession(this.toPublicSession(session));
  }

  /**
   * Reject a pending plan
   */
  async rejectTask(sessionId: string, feedback?: string): Promise<void> {
    const session = this.sessions.get(sessionId);

    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    if (session.state !== "awaiting_approval") {
      throw new Error(
        `Session ${sessionId} is not awaiting approval (current state: ${session.state})`
      );
    }

    // Update plan status
    if (session.plan) {
      session.plan.status = "rejected";

      // Add to revision history
      if (!session.plan.revisions) {
        session.plan.revisions = [];
      }

      session.plan.revisions.push({
        version: session.plan.version,
        createdAt: session.plan.createdAt,
        rejectedAt: new Date().toISOString(),
        rejectedReason: feedback,
        contentPath: session.plan.contentPath || "",
      });
    }

    // Transition to cancelled state
    this.transitionState(session, "cancelled");

    // Resolve the approval promise with rejection
    if (session.approvalResolver) {
      session.approvalResolver(false);
      session.approvalResolver = undefined;
    }

    // Persist
    await this.config.stateStore.saveSession(this.toPublicSession(session));
  }

  /**
   * Request plan revision
   */
  async revisePlan(sessionId: string, feedback: string): Promise<void> {
    const session = this.sessions.get(sessionId);

    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    if (session.state !== "awaiting_approval") {
      throw new Error(
        `Session ${sessionId} is not awaiting approval (current state: ${session.state})`
      );
    }

    // Update plan status
    if (session.plan) {
      session.plan.status = "rejected";

      // Add to revision history
      if (!session.plan.revisions) {
        session.plan.revisions = [];
      }

      session.plan.revisions.push({
        version: session.plan.version,
        createdAt: session.plan.createdAt,
        rejectedAt: new Date().toISOString(),
        rejectedReason: feedback,
        contentPath: session.plan.contentPath || "",
      });
    }

    // Transition to plan revision state
    this.transitionState(session, "plan_revision");

    // Resolve the revision promise to trigger re-planning
    if (session.revisionResolver) {
      session.revisionResolver(true);
      session.revisionResolver = undefined;
    }

    // Persist
    await this.config.stateStore.saveSession(this.toPublicSession(session));
  }

  /**
   * Cancel a task
   */
  async cancelTask(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId);

    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    // Transition to cancelled
    this.transitionState(session, "cancelled");

    // Clean up any pending promises
    if (session.approvalResolver) {
      session.approvalResolver(false);
      session.approvalResolver = undefined;
    }

    if (session.revisionResolver) {
      session.revisionResolver(false);
      session.revisionResolver = undefined;
    }

    // Persist
    await this.config.stateStore.saveSession(this.toPublicSession(session));
  }

  /**
   * Get session state
   */
  async getSession(sessionId: string): Promise<TaskSession | null> {
    const session = this.sessions.get(sessionId);

    if (!session) {
      // Try loading from state store
      return await this.config.stateStore.loadSession(sessionId);
    }

    return this.toPublicSession(session);
  }

  /**
   * Get current workflow phase
   */
  async getCurrentPhase(sessionId: string): Promise<WorkflowPhase> {
    const session = this.sessions.get(sessionId);

    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    // Map state to phase
    switch (session.state) {
      case "researching":
        return "research";
      case "clarifying":
      case "planning":
      case "awaiting_approval":
      case "plan_revision":
        return "planning";
      case "executing":
        return "implementation";
      case "validating":
        return "validation";
      default:
        return "planning"; // Default fallback
    }
  }

  /**
   * Subscribe to workflow updates
   */
  async *subscribeToUpdates(sessionId: string): AsyncIterableIterator<WorkflowUpdate> {
    const session = this.sessions.get(sessionId);

    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    const emitter = session.eventEmitter;
    const updateQueue: WorkflowUpdate[] = [];
    let resolveNext: ((value: IteratorResult<WorkflowUpdate>) => void) | null = null;
    let done = false;

    // Set up event listener
    const onUpdate = (update: WorkflowUpdate) => {
      if (resolveNext) {
        const resolver = resolveNext;
        resolveNext = null;
        resolver({ value: update, done: false });
      } else {
        updateQueue.push(update);
      }
    };

    const onComplete = () => {
      done = true;
      if (resolveNext) {
        const resolver = resolveNext;
        resolveNext = null;
        resolver({ value: undefined as any, done: true });
      }
    };

    emitter.on("update", onUpdate);
    emitter.on("complete", onComplete);

    try {
      while (true) {
        if (updateQueue.length > 0) {
          yield updateQueue.shift()!;
          continue;
        }

        if (done) {
          break;
        }

        const result = await new Promise<IteratorResult<WorkflowUpdate>>((resolve) => {
          resolveNext = resolve;
        });

        if (result.done) {
          done = true;
          break;
        }

        yield result.value;
      }
    } finally {
      emitter.off("update", onUpdate);
      emitter.off("complete", onComplete);
    }
  }

  // =============================================================================
  // Private Methods
  // =============================================================================

  /**
   * Execute the appropriate workflow based on mode
   */
  private async executeWorkflow(session: InternalSession): Promise<void> {
    try {
      // Select workflow based on mode
      const workflow =
        session.mode === "editor" ? this.config.editorWorkflow : this.config.architectWorkflow;

      // Execute workflow and stream updates
      const iterator = workflow.execute(session.input);
      session.workflowIterator = iterator;

      for await (const update of iterator) {
        // Stop processing if session was cancelled
        if (session.state === "cancelled") {
          break;
        }

        // Handle state changes
        if (update.type === "state_change") {
          this.transitionState(session, update.data.state);
        }

        // Handle plan updates
        if (update.type === "progress" && update.data.phase === "planning" && update.data.plan) {
          session.plan = update.data.plan;
          const contentPath = await this.config.stateStore.savePlan(session.id, session.plan);
          // Update in-memory session with contentPath so subsequent saves preserve it
          session.plan.contentPath = contentPath;
        }

        // Handle research updates
        if (update.type === "progress" && update.data.phase === "research" && update.data.result) {
          session.research = update.data.result;
        }

        // Handle clarification updates
        if (
          update.type === "progress" &&
          update.data.phase === "clarification" &&
          update.data.result
        ) {
          session.clarification = update.data.result;
        }

        // Emit update to subscribers
        session.eventEmitter.emit("update", update);

        // Handle approval blocking
        if (session.state === "awaiting_approval") {
          // Wait for user approval/rejection
          const approved = await new Promise<boolean>((resolve) => {
            session.approvalResolver = resolve;
          });

          if (!approved) {
            // User rejected or cancelled
            break;
          }
        }

        // Handle plan revision
        if (session.state === "plan_revision") {
          // Wait for revision to be requested
          const shouldRevise = await new Promise<boolean>((resolve) => {
            session.revisionResolver = resolve;
          });

          if (!shouldRevise) {
            // User cancelled
            break;
          }
        }

        // Persist session periodically
        await this.config.stateStore.saveSession(this.toPublicSession(session));
      }

      // Mark as complete
      if (session.state !== "cancelled" && session.state !== "error") {
        this.transitionState(session, "complete");
        session.metadata.completedAt = new Date().toISOString();
      }

      // Emit completion
      session.eventEmitter.emit("complete");

      // Final persistence
      await this.config.stateStore.saveSession(this.toPublicSession(session));
    } catch (error) {
      console.error(`[Orchestrator] Workflow execution error:`, error);
      this.transitionState(session, "error");

      // Emit error update
      session.eventEmitter.emit("update", {
        type: "error",
        sessionId: session.id,
        timestamp: new Date().toISOString(),
        data: {
          error: error instanceof Error ? error.message : String(error),
        },
      });

      session.eventEmitter.emit("complete");

      // Persist error state
      await this.config.stateStore.saveSession(this.toPublicSession(session));
    }
  }

  /**
   * Transition session to a new state
   */
  private transitionState(session: InternalSession, newState: WorkflowState): void {
    const oldState = session.state;
    session.state = newState;

    console.error(`[Orchestrator] Session ${session.id}: ${oldState} → ${newState}`);

    // Emit state change event
    session.eventEmitter.emit("update", {
      type: "state_change",
      sessionId: session.id,
      timestamp: new Date().toISOString(),
      data: { state: newState, previousState: oldState },
    });
  }

  /**
   * Generate a unique session ID
   */
  private generateSessionId(): string {
    const timestamp = Date.now();
    const random = randomBytes(3).toString("hex");
    return `sess_${timestamp}_${random}`;
  }

  /**
   * Convert internal session to public session
   */
  private toPublicSession(session: InternalSession): TaskSession {
    const {
      eventEmitter: _eventEmitter,
      workflowIterator: _workflowIterator,
      approvalResolver: _approvalResolver,
      revisionResolver: _revisionResolver,
      ...publicSession
    } = session;
    return publicSession;
  }
}
