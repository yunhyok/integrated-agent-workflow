import { existsSync } from "node:fs";
import { join } from "node:path";
import { adapters } from "../adapters/index.js";
import { pluginIdentity } from "../common/result-schema.js";
import { runProcess } from "../common/process-runner.js";

export interface DoctorOptions {
  cwd: string;
  runVersionCheck: boolean;
  now?: Date;
}

export interface DoctorAgentStatus {
  id: string;
  displayName: string;
  binaryName: string;
  status: "available" | "unavailable";
  version?: string;
  authHint: string;
}

export interface DoctorReport {
  plugin: typeof pluginIdentity;
  checkedAt: string;
  cwd: string;
  cachePath: string;
  agents: DoctorAgentStatus[];
}

export async function createDoctorReport(options: DoctorOptions): Promise<DoctorReport> {
  const agents: DoctorAgentStatus[] = [];

  for (const adapter of Object.values(adapters)) {
    let version: string | undefined;
    let status: "available" | "unavailable" = "unavailable";

    if (options.runVersionCheck) {
      const result = await runProcess(adapter.binaryName, adapter.versionArgs, {
        cwd: options.cwd,
        timeoutMs: 5_000
      });
      status = result.status === "ok" ? "available" : "unavailable";
      version = result.stdout.trim() || undefined;
    }

    agents.push({
      id: adapter.id,
      displayName: adapter.displayName,
      binaryName: adapter.binaryName,
      status,
      version,
      authHint: adapter.authHint
    });
  }

  return {
    plugin: pluginIdentity,
    checkedAt: (options.now ?? new Date()).toISOString(),
    cwd: options.cwd,
    cachePath: join(options.cwd, ".codex", "multi-agent", "cache", "doctor.json"),
    agents
  };
}

export function hasDoctorCache(cwd: string): boolean {
  return existsSync(join(cwd, ".codex", "multi-agent", "cache", "doctor.json"));
}
