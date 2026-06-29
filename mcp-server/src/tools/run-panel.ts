import type { AgentResult } from "../common/result-schema.js";

export type PanelStatus = "success" | "partial_success" | "failed";

export function summarizePanelStatus(results: AgentResult[]): PanelStatus {
  const okCount = results.filter((result) => result.status === "ok").length;
  if (okCount === results.length && results.length > 0) return "success";
  if (okCount > 0) return "partial_success";
  return "failed";
}
