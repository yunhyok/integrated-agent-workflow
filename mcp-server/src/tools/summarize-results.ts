import type { AgentResult } from "../common/result-schema.js";

export interface ResultSummary {
  okAgents: string[];
  failedAgents: Array<{ agent: string; status: string; message?: string }>;
  combinedText: string;
}

export function summarizeResults(results: AgentResult[]): ResultSummary {
  return {
    okAgents: results.filter((result) => result.status === "ok").map((result) => result.displayName),
    failedAgents: results
      .filter((result) => result.status !== "ok")
      .map((result) => ({ agent: result.displayName, status: result.status, message: result.errorMessage })),
    combinedText: results
      .filter((result) => result.resultText.trim().length > 0)
      .map((result) => `## ${result.displayName}\n\n${result.resultText}`)
      .join("\n\n")
  };
}
