/**
 * Simple markdown → TOML plan parser
 *
 * Parses Claude's markdown plan into structured data for TOML serialization.
 * Much more reliable than having the LLM generate TOML directly.
 */

export interface ParsedTask {
  id: string;
  description: string;
  files: string[];
  phase: number;
  dependencies: string[];
}

export interface ParsedPlan {
  title: string;
  tasks: ParsedTask[];
  phases: Array<{ name: string; order: number }>;
}

/**
 * Parse markdown plan into structured format
 *
 * Expected format:
 * ## Plan: [Title]
 *
 * ### Phase 1: [Name]
 * - Task: [Description] (Files: path/to/file.ts)
 * - Task: [Description] (Files: file1.ts, file2.ts)
 *
 * ### Phase 2: [Name]
 * - Task: [Description] (Files: path/to/file.ts)
 */
export function parseMarkdownPlan(markdown: string): ParsedPlan {
  const lines = markdown.split('\n');

  let title = "Untitled Plan";
  const phases: Array<{ name: string; order: number }> = [];
  const tasks: ParsedTask[] = [];

  let currentPhase = 0;
  let taskCounter = 1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    // Extract title: ## Plan: Title
    const titleMatch = line.match(/^##\s*Plan:\s*(.+)/i);
    if (titleMatch) {
      title = titleMatch[1].trim();
      continue;
    }

    // Extract phase: ### Phase N: Name
    const phaseMatch = line.match(/^###\s*Phase\s+(\d+):\s*(.+)/i);
    if (phaseMatch) {
      currentPhase = parseInt(phaseMatch[1]);
      const phaseName = phaseMatch[2].trim();
      phases.push({ name: phaseName, order: currentPhase });
      continue;
    }

    // Extract task: - Task: Description (Files: file1.ts, file2.ts)
    const taskMatch = line.match(/^-\s*(?:Task:\s*)?(.+?)(?:\s*\(Files?:\s*(.+?)\))?$/i);
    if (taskMatch && currentPhase > 0) {
      const description = taskMatch[1].trim();
      const filesStr = taskMatch[2] || "";
      const files = filesStr
        .split(',')
        .map(f => f.trim())
        .filter(f => f.length > 0);

      tasks.push({
        id: `task-${taskCounter}`,
        description,
        files,
        phase: currentPhase,
        dependencies: []
      });

      taskCounter++;
    }
  }

  // Fallback: If no structured plan found, treat entire response as single task
  if (tasks.length === 0) {
    console.error("[Parser] No structured tasks found, creating fallback task");
    tasks.push({
      id: "task-1",
      description: "Implement based on discussion",
      files: [],
      phase: 1,
      dependencies: []
    });
    phases.push({ name: "Implementation", order: 1 });
  }

  return { title, tasks, phases };
}

/**
 * Detect if user message is confirming the plan
 */
export function isConfirmation(message: string): boolean {
  const confirmPatterns = [
    /\b(confirm|approved?|lgtm|looks? good|proceed|save|let'?s go)\b/i,
    /\b(yes,?\s*(please|do it|go ahead))\b/i,
    /\b(perfect|great|sounds good)\b/i
  ];

  const rejectPatterns = [
    /\b(no|cancel|stop|nevermind|wait|hold on)\b/i
  ];

  // Check for rejection first
  if (rejectPatterns.some(pattern => pattern.test(message))) {
    return false;
  }

  // Check for confirmation
  return confirmPatterns.some(pattern => pattern.test(message));
}
