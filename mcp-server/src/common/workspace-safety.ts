import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import type { WritePolicy } from "./result-schema.js";

export interface WorkspaceState {
  gitRepository: boolean;
  dirty: boolean;
  linkedWorktree: boolean;
  isolatedWriteAvailable: boolean;
}

export interface WorkspaceSafety {
  allowed: boolean;
  status: "allowed" | "unsafe_request";
  reason: string;
  workspace: WorkspaceState;
}

function defaultWorkspaceState(): WorkspaceState {
  return {
    gitRepository: false,
    dirty: false,
    linkedWorktree: false,
    isolatedWriteAvailable: false
  };
}

function runGit(cwd: string, args: string[]): { ok: boolean; stdout: string } {
  try {
    const result = spawnSync("git", args, {
      cwd,
      shell: false,
      encoding: "utf8",
      windowsHide: true
    });
    return {
      ok: result.status === 0,
      stdout: typeof result.stdout === "string" ? result.stdout.trim() : ""
    };
  } catch {
    return { ok: false, stdout: "" };
  }
}

export function getWorkspaceState(cwd: string): WorkspaceState {
  const insideWorkTree = runGit(cwd, ["rev-parse", "--is-inside-work-tree"]);
  if (!insideWorkTree.ok || insideWorkTree.stdout !== "true") {
    return defaultWorkspaceState();
  }

  const status = runGit(cwd, ["status", "--short"]);
  const gitDir = runGit(cwd, ["rev-parse", "--git-dir"]);
  const commonDir = runGit(cwd, ["rev-parse", "--git-common-dir"]);
  const linkedWorktree =
    gitDir.ok &&
    commonDir.ok &&
    gitDir.stdout.length > 0 &&
    commonDir.stdout.length > 0 &&
    resolve(cwd, gitDir.stdout) !== resolve(cwd, commonDir.stdout);

  return {
    gitRepository: true,
    dirty: status.ok ? status.stdout.length > 0 : false,
    linkedWorktree,
    isolatedWriteAvailable: linkedWorktree
  };
}

export function evaluateWorkspaceSafety(cwd: string, writePolicy: WritePolicy): WorkspaceSafety {
  const workspace = getWorkspaceState(cwd);

  if (writePolicy === "isolated_write" && !workspace.isolatedWriteAvailable) {
    return {
      allowed: false,
      status: "unsafe_request",
      reason: "isolated_write requires an isolated linked worktree",
      workspace
    };
  }

  if (writePolicy === "read_only") {
    return {
      allowed: true,
      status: "allowed",
      reason: "read_only is a prompt-level policy; external agents must not modify files",
      workspace
    };
  }

  if (writePolicy === "patch_proposal") {
    return {
      allowed: true,
      status: "allowed",
      reason: "patch_proposal is a prompt-level policy; external agents may propose changes but must not apply them",
      workspace
    };
  }

  return {
    allowed: true,
    status: "allowed",
    reason: "isolated_write is allowed in this linked worktree",
    workspace
  };
}
