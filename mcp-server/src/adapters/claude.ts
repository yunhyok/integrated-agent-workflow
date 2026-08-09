import type { CliAdapter } from "./types.js";

export const claudeAdapter: CliAdapter = {
  id: "claude",
  displayName: "Claude Code",
  binaryName: "claude",
  versionArgs: ["--version"],
  authHint: "Run the Claude CLI login command, then rerun doctor.",
  buildCommand(prompt, options) {
    const permissionMode = options.writePolicy === "isolated_write" ? "acceptEdits" : "plan";
    const args = [
      "--permission-mode",
      permissionMode,
      "--output-format",
      "json",
      "--no-session-persistence"
    ];
    if (options.requestedModel) args.push("--model", options.requestedModel);
    args.push("-p");
    return {
      command: "claude",
      args,
      input: prompt
    };
  }
};
