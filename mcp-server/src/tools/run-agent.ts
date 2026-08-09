import type { AgentId, AgentPurpose, AgentStatus, WritePolicy } from "../common/result-schema.js";
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
  return /\b(not logged in|not signed in|login required|unauthenticated|authentication|auth method)\b/i.test(output);
}

interface ParsedClaudeOutput {
  resultText: string;
  observedModels: string[];
  isError: boolean;
}

export function parseClaudeJsonOutput(output: string): ParsedClaudeOutput | undefined {
  try {
    const value: unknown = JSON.parse(output.trim());
    if (!value || typeof value !== "object") return undefined;

    const record = value as Record<string, unknown>;
    if (typeof record.result !== "string") return undefined;

    const modelUsage = record.modelUsage;
    const observedModels =
      modelUsage && typeof modelUsage === "object" && !Array.isArray(modelUsage)
        ? Object.keys(modelUsage as Record<string, unknown>).sort()
        : [];
    const subtype = typeof record.subtype === "string" ? record.subtype : "";
    const isError =
      record.is_error === true ||
      record.api_error_status !== null && record.api_error_status !== undefined ||
      subtype.startsWith("error");

    return { resultText: record.result, observedModels, isError };
  } catch {
    return undefined;
  }
}

function compareRequestedModel(requestedModel: string | undefined, observedModels: string[]) {
  if (!requestedModel || observedModels.length === 0) return "unverified" as const;
  return observedModels.includes(requestedModel) ? ("confirmed" as const) : ("mismatch" as const);
}

export function normalizeExecutionResult(input: {
  agentId: AgentId;
  displayName: string;
  requestedModel?: string;
  processResult: ProcessRunResult;
  logPath?: string;
}) {
  const output = `${input.processResult.stderr}\n${input.processResult.stdout}`;
  let status: AgentStatus =
    input.processResult.status === "ok"
      ? "ok"
      : input.processResult.status === "execution_failed" && isAuthenticationFailure(output)
        ? "unauthenticated"
        : input.processResult.status;

  const claudeOutput =
    input.agentId === "claude" && input.processResult.status === "ok"
      ? parseClaudeJsonOutput(input.processResult.stdout)
      : undefined;
  if (input.agentId === "claude" && input.processResult.status === "ok" && !claudeOutput) {
    status = "invalid_output";
  } else if (claudeOutput?.isError) {
    status = isAuthenticationFailure(claudeOutput.resultText) ? "unauthenticated" : "execution_failed";
  }

  const observedModels = claudeOutput?.observedModels;

  return makeAgentResult({
    agentId: input.agentId,
    displayName: input.displayName,
    requestedModel: input.requestedModel,
    observedModels,
    modelMatch: compareRequestedModel(input.requestedModel, observedModels ?? []),
    modelObservationSource: observedModels?.length ? "claude_cli_json_modelUsage" : undefined,
    status,
    durationMs: input.processResult.durationMs,
    exitCode: input.processResult.exitCode,
    stdout: input.processResult.stdout,
    stderrSummary: input.processResult.stderr.trim().slice(0, 1000),
    resultText: claudeOutput?.resultText ?? input.processResult.stdout.trim(),
    logPath: input.logPath,
    errorMessage:
      status === "invalid_output"
        ? "Claude CLI returned output that was not valid result JSON."
        : claudeOutput?.isError
          ? `Claude CLI reported an error result: ${claudeOutput.resultText.trim().slice(0, 1000)}`
          : undefined
  });
}

export function makeUnsafeWorkspaceResult(input: {
  agentId: AgentId;
  displayName: string;
  requestedModel?: string;
  reason: string;
}) {
  return makeAgentResult({
    agentId: input.agentId,
    displayName: input.displayName,
    requestedModel: input.requestedModel,
    status: "unsafe_request",
    durationMs: 0,
    resultText: "",
    errorMessage: input.reason
  });
}
