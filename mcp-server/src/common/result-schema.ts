export const pluginIdentity = {
  name: "Integrated Agent Workflow",
  packageName: "integrated-agent-workflow",
  version: "0.5.0"
} as const;

export const AGENT_STATUSES = [
  "ok",
  "unavailable",
  "unauthenticated",
  "timeout",
  "execution_failed",
  "invalid_output",
  "unsafe_request"
] as const;

export type AgentStatus = (typeof AGENT_STATUSES)[number];
export type AgentId = "codex" | "lmstudio" | "claude" | "copilot" | "antigravity";
export type AgentPurpose = "implementation" | "review" | "general";
export type WritePolicy = "read_only" | "patch_proposal" | "isolated_write";
export type ModelMatch = "confirmed" | "mismatch" | "unverified";
export type ModelObservationSource = "claude_cli_json_modelUsage";

export interface AgentResult {
  plugin: typeof pluginIdentity;
  agentId: AgentId;
  displayName: string;
  requestedModel?: string;
  observedModels?: string[];
  modelMatch: ModelMatch;
  modelObservationSource?: ModelObservationSource;
  status: AgentStatus;
  createdAt: string;
  durationMs: number;
  exitCode?: number | null;
  stdout?: string;
  stderrSummary?: string;
  resultText: string;
  logPath?: string;
  errorMessage?: string;
}

export interface AgentResultInput {
  agentId: AgentId;
  displayName: string;
  requestedModel?: string;
  observedModels?: string[];
  modelMatch?: ModelMatch;
  modelObservationSource?: ModelObservationSource;
  status: AgentStatus;
  durationMs: number;
  exitCode?: number | null;
  stdout?: string;
  stderrSummary?: string;
  resultText?: string;
  logPath?: string;
  errorMessage?: string;
}

export function makeAgentResult(input: AgentResultInput): AgentResult {
  return {
    plugin: pluginIdentity,
    agentId: input.agentId,
    displayName: input.displayName,
    requestedModel: input.requestedModel,
    observedModels: input.observedModels,
    modelMatch: input.modelMatch ?? "unverified",
    modelObservationSource: input.modelObservationSource,
    status: input.status,
    createdAt: new Date().toISOString(),
    durationMs: input.durationMs,
    exitCode: input.exitCode,
    stdout: input.stdout,
    stderrSummary: input.stderrSummary,
    resultText: input.resultText ?? "",
    logPath: input.logPath,
    errorMessage: input.errorMessage
  };
}
