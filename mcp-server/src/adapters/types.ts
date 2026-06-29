import type { AgentId, AgentResult } from "../common/result-schema.js";

export interface BuiltCommand {
  command: string;
  args: string[];
  input?: string;
}

export interface BuildCommandOptions {
  timeoutMs: number;
}

export interface CliAdapter {
  id: AgentId;
  displayName: string;
  binaryName: string;
  versionArgs: string[];
  authHint: string;
  buildCommand(prompt: string, options: BuildCommandOptions): BuiltCommand;
}

export interface AgentExecutionRequest {
  cwd: string;
  prompt: string;
  timeoutMs: number;
}

export type AgentExecutionResponse = AgentResult;
