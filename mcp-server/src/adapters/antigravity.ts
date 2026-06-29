import type { CliAdapter } from "./types.js";

export const antigravityAdapter: CliAdapter = {
  id: "antigravity",
  displayName: "Google Antigravity CLI",
  binaryName: "agy",
  versionArgs: ["--version"],
  authHint: "Run the Antigravity CLI auth or login command, then rerun doctor.",
  buildCommand(prompt) {
    return {
      command: "agy",
      args: ["--prompt"],
      input: prompt
    };
  }
};
