import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, isAbsolute, join } from "node:path";
import { redactSecrets } from "./redaction.js";

export interface ProcessRunOptions {
  cwd: string;
  timeoutMs: number;
  input?: string;
  inputMode?: "stdin" | "temporary_file";
}

export interface ProcessRunResult {
  status: "ok" | "timeout" | "execution_failed" | "unavailable";
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export interface ResolvedProcessCommand {
  command: string;
  args: string[];
}

export interface ResolveProcessCommandOptions {
  platform?: NodeJS.Platform;
  arch?: string;
  env?: NodeJS.ProcessEnv;
}

function findNativeOnPath(command: string, env: NodeJS.ProcessEnv): string | undefined {
  const pathValue = env.Path ?? env.PATH ?? "";
  for (const directory of pathValue.split(delimiter).filter(Boolean)) {
    for (const extension of [".exe", ".com"]) {
      const candidate = join(directory, `${command}${extension}`);
      if (existsSync(candidate)) return candidate;
    }
  }
  return undefined;
}

export function resolveProcessCommand(
  command: string,
  args: string[],
  options: ResolveProcessCommandOptions = {}
): ResolvedProcessCommand {
  const platform = options.platform ?? process.platform;
  if (platform !== "win32" || isAbsolute(command) || /[\\/]/.test(command)) {
    return { command, args };
  }

  const env = options.env ?? process.env;
  const nativeOnPath = findNativeOnPath(command, env);
  if (nativeOnPath) return { command: nativeOnPath, args };

  const appData = env.APPDATA;
  const localAppData = env.LOCALAPPDATA;
  const arch = options.arch ?? process.arch;
  const nativeCandidates: Record<string, Array<string | undefined>> = {
    codex: [localAppData && join(localAppData, "OpenAI", "Codex", "bin", "codex.exe")],
    claude: [
      appData && join(appData, "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
    ],
    copilot: [
      appData &&
        join(
          appData,
          "npm",
          "node_modules",
          "@github",
          "copilot",
          "node_modules",
          "@github",
          `copilot-win32-${arch}`,
          "copilot.exe"
        )
    ],
    agy: [localAppData && join(localAppData, "agy", "bin", "agy.exe")]
  };

  for (const candidate of nativeCandidates[command] ?? []) {
    if (candidate && existsSync(candidate)) return { command: candidate, args };
  }

  return { command, args };
}

export function runProcess(command: string, args: string[], options: ProcessRunOptions): Promise<ProcessRunResult> {
  const startedAt = Date.now();
  let temporaryDirectory: string | undefined;
  let processArgs = args;
  if (options.inputMode === "temporary_file" && options.input) {
    temporaryDirectory = mkdtempSync(join(tmpdir(), "integrated-agent-prompt-"));
    const promptFile = join(temporaryDirectory, "brief.txt");
    writeFileSync(promptFile, options.input, { encoding: "utf8", mode: 0o600 });
    processArgs = args.map((arg) =>
      arg.replaceAll("{{PROMPT_FILE}}", promptFile).replaceAll("{{PROMPT_DIR}}", temporaryDirectory!)
    );
  }
  const resolved = resolveProcessCommand(command, processArgs);

  const cleanupTemporaryDirectory = () => {
    if (!temporaryDirectory) return;
    try {
      rmSync(temporaryDirectory, { recursive: true, force: true, maxRetries: 3, retryDelay: 50 });
      temporaryDirectory = undefined;
    } catch {
      // Best-effort cleanup; no prompt content is copied into the result.
    }
  };

  return new Promise((resolve) => {
    const child = spawn(resolved.command, resolved.args, {
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
      cleanupTemporaryDirectory();
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
      cleanupTemporaryDirectory();
      resolve({
        status: error.code === "ENOENT" ? "unavailable" : "execution_failed",
        exitCode: null,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(`${stderr}\n${error.message}`),
        durationMs: Date.now() - startedAt
      });
    });

    child.on("close", (code) => {
      if (settled) {
        cleanupTemporaryDirectory();
        return;
      }
      settled = true;
      clearTimeout(timer);
      cleanupTemporaryDirectory();
      resolve({
        status: code === 0 ? "ok" : "execution_failed",
        exitCode: code,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(stderr),
        durationMs: Date.now() - startedAt
      });
    });

    if (options.input && options.inputMode !== "temporary_file") {
      child.stdin.write(options.input);
    }
    child.stdin.end();
  });
}
