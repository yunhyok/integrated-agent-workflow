import type { CliAdapter } from "./types.js";

export const claudeAdapter: CliAdapter = {
  id: "claude",
  displayName: "Claude Code",
  binaryName: "claude",
  versionArgs: ["--version"],
  authHint: "Run the Claude CLI login command, then rerun doctor.",
  buildCommand(prompt) {
    return {
      command: "claude",
      args: ["-p"],
      input: prompt
    };
  }
};
