import type { AgentId, AgentPurpose, WritePolicy } from "../common/result-schema.js";
import { makeAgentResult } from "../common/result-schema.js";
import type { ProcessRunResult } from "../common/process-runner.js";
import { redactSecrets } from "../common/redaction.js";

export interface BuildAgentPromptInput {
  task: string;
  purpose: AgentPurpose;
  acceptanceCriteria: string[];
  writePolicy: WritePolicy;
}

export function buildAgentPrompt(input: BuildAgentPromptInput): string {
  const task = redactSecrets(input.task);
  const acceptanceCriteria = input.acceptanceCriteria.map((item) => redactSecrets(item));
  return [
    `Purpose: ${input.purpose}`,
    `Task: ${task}`,
    `Required write policy: ${input.writePolicy}`,
    "",
    "Acceptance criteria:",
    ...acceptanceCriteria.map((item) => `- ${item}`),
    "",
    "Return concise findings, proposed changes, risks, and tests. Do not claim you ran checks unless you actually ran them."
  ].join("\n");
}

export function isAuthenticationFailure(output: string): boolean {
  return /\b(not logged in|login required|unauthenticated|authentication)\b/i.test(output);
}

export function normalizeExecutionResult(input: {
  agentId: AgentId;
  displayName: string;
  processResult: ProcessRunResult;
  logPath?: string;
}) {
  const output = `${input.processResult.stderr}\n${input.processResult.stdout}`;
  const status =
    input.processResult.status === "ok"
      ? "ok"
      : input.processResult.status === "execution_failed" && isAuthenticationFailure(output)
        ? "unauthenticated"
        : input.processResult.status;

  return makeAgentResult({
    agentId: input.agentId,
    displayName: input.displayName,
    status,
    durationMs: input.processResult.durationMs,
    exitCode: input.processResult.exitCode,
    stdout: input.processResult.stdout,
    stderrSummary: input.processResult.stderr.trim().slice(0, 1000),
    resultText: input.processResult.stdout.trim(),
    logPath: input.logPath
  });
}

export function makeUnsafeWorkspaceResult(input: {
  agentId: AgentId;
  displayName: string;
  reason: string;
}) {
  return makeAgentResult({
    agentId: input.agentId,
    displayName: input.displayName,
    status: "unsafe_request",
    durationMs: 0,
    resultText: "",
    errorMessage: input.reason
  });
}
