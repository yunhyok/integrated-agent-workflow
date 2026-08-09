import type { CliAdapter } from "./types.js";

export const copilotAdapter: CliAdapter = {
  id: "copilot",
  displayName: "GitHub Copilot CLI",
  binaryName: "copilot",
  versionArgs: ["--version"],
  authHint: "Run the Copilot CLI auth or login command, then rerun doctor.",
  buildCommand(prompt, options) {
    const args = ["--silent", "--no-ask-user"];
    if (options.writePolicy !== "isolated_write") args.push("--plan");
    else args.push("--allow-all-tools");
    if (options.requestedModel) args.push("--model", options.requestedModel);
    return {
      command: "copilot",
      args,
      input: prompt
    };
  }
};
