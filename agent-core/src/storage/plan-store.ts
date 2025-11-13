// agent-core/src/storage/plan-store.ts
import { Plan, PlanSchema } from "../../../../shared/types/state";
import { TOMLWriter } from "./toml-writer";
import * as path from "path";
import * as fs from "fs/promises";

export class PlanStore {
  private stateDir: string;
  private workspaceRoot: string;

  constructor(workspaceRoot: string) {
    this.workspaceRoot = workspaceRoot;
    this.stateDir = path.join(workspaceRoot, ".dolphin", "state", "plans");
  }

  async savePlan(plan: Plan): Promise<void> {
    // Validate schema
    const validated = PlanSchema.parse(plan);

    // Update timestamp
    validated.plan.updated_at = new Date().toISOString();

    const filepath = path.join(this.stateDir, `${plan.plan.id}.toml`);
    const writer = new TOMLWriter<Plan>(filepath, this.workspaceRoot);

    await writer.write(validated);

    console.error(`[PlanStore] Saved plan: ${plan.plan.id}`);
  }

  async loadPlan(planId: string): Promise<Plan | null> {
    const filepath = path.join(this.stateDir, `${planId}.toml`);
    const writer = new TOMLWriter<Plan>(filepath, this.workspaceRoot);

    const data = await writer.read();
    if (!data) {
      return null;
    }

    // Validate on read
    return PlanSchema.parse(data);
  }

  async listPlans(): Promise<string[]> {
    try {
      await fs.mkdir(this.stateDir, { recursive: true });
      const files = await fs.readdir(this.stateDir);
      return files
        .filter((f) => f.endsWith(".toml"))
        .map((f) => f.replace(".toml", ""))
        .sort();
    } catch {
      return [];
    }
  }

  async deletePlan(planId: string): Promise<void> {
    const filepath = path.join(this.stateDir, `${planId}.toml`);
    const writer = new TOMLWriter<Plan>(filepath, this.workspaceRoot);
    await writer.delete();

    console.error(`[PlanStore] Deleted plan: ${planId}`);
  }

  async getLatestPlan(): Promise<Plan | null> {
    const plans = await this.listPlans();
    if (plans.length === 0) {
      return null;
    }

    return this.loadPlan(plans[plans.length - 1]);
  }
}
