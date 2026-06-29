import type { AgentId, AgentPurpose, WritePolicy } from "../common/result-schema.js";
import { makeAgentResult } from "../common/result-schema.js";
import type { ProcessRunResult } from "../common/process-runner.js";

export interface BuildAgentPromptInput {
  task: string;
  purpose: AgentPurpose;
  acceptanceCriteria: string[];
  writePolicy: WritePolicy;
}

export function buildAgentPrompt(input: BuildAgentPromptInput): string {
  return [
    `Purpose: ${input.purpose}`,
    `Task: ${input.task}`,
    `Required write policy: ${input.writePolicy}`,
    "",
    "Acceptance criteria:",
    ...input.acceptanceCriteria.map((item) => `- ${item}`),
    "",
    "Return concise findings, proposed changes, risks, and tests. Do not claim you ran checks unless you actually ran them."
  ].join("\n");
}

export function normalizeExecutionResult(input: {
  agentId: AgentId;
  displayName: string;
  processResult: ProcessRunResult;
}) {
  return makeAgentResult({
    agentId: input.agentId,
    displayName: input.displayName,
    status: input.processResult.status === "ok" ? "ok" : input.processResult.status,
    durationMs: input.processResult.durationMs,
    exitCode: input.processResult.exitCode,
    stdout: input.processResult.stdout,
    stderrSummary: input.processResult.stderr.trim().slice(0, 1000),
    resultText: input.processResult.stdout.trim()
  });
}
