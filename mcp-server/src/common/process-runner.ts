import { spawn } from "node:child_process";
import { redactSecrets } from "./redaction.js";

export interface ProcessRunOptions {
  cwd: string;
  timeoutMs: number;
  input?: string;
}

export interface ProcessRunResult {
  status: "ok" | "timeout" | "execution_failed" | "unavailable";
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export function runProcess(command: string, args: string[], options: ProcessRunOptions): Promise<ProcessRunResult> {
  const startedAt = Date.now();

  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill("SIGTERM");
      resolve({
        status: "timeout",
        exitCode: null,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(stderr),
        durationMs: Date.now() - startedAt
      });
    }, options.timeoutMs);

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });

    child.on("error", (error: NodeJS.ErrnoException) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        status: error.code === "ENOENT" ? "unavailable" : "execution_failed",
        exitCode: null,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(`${stderr}\n${error.message}`),
        durationMs: Date.now() - startedAt
      });
    });

    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        status: code === 0 ? "ok" : "execution_failed",
        exitCode: code,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(stderr),
        durationMs: Date.now() - startedAt
      });
    });

    if (options.input) {
      child.stdin.write(options.input);
    }
    child.stdin.end();
  });
}
