import type { CliAdapter } from "./types.js";

export const copilotAdapter: CliAdapter = {
  id: "copilot",
  displayName: "GitHub Copilot CLI",
  binaryName: "copilot",
  versionArgs: ["--version"],
  authHint: "Run the Copilot CLI auth or login command, then rerun doctor.",
  buildCommand(prompt) {
    return {
      command: "copilot",
      args: ["--prompt", prompt]
    };
  }
};
