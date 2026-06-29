import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import type { AgentId } from "./result-schema.js";
import { redactSecrets } from "./redaction.js";

function safeTimestamp(date = new Date()): string {
  return date.toISOString().replace(/[:.]/g, "-");
}

export function writeRunArtifact(cwd: string, agentId: AgentId, payload: unknown): string {
  const runId = `${safeTimestamp()}-${randomBytes(4).toString("hex")}`;
  const runDir = join(cwd, ".codex", "multi-agent", "runs", runId);
  mkdirSync(runDir, { recursive: true });

  const logPath = join(runDir, "result.json");
  const serialized = JSON.stringify({ agentId, payload }, null, 2);
  writeFileSync(logPath, redactSecrets(serialized), "utf8");
  return logPath;
}
