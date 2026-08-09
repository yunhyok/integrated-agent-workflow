import type { CliAdapter } from "./types.js";

export const antigravityAdapter: CliAdapter = {
  id: "antigravity",
  displayName: "Google Antigravity CLI",
  binaryName: "agy",
  versionArgs: ["--version"],
  authHint: "Run the Antigravity CLI auth or login command, then rerun doctor.",
  buildCommand(prompt, options) {
    const mode = options.writePolicy === "isolated_write" ? "accept-edits" : "plan";
    const args = ["--mode", mode];
    if (options.requestedModel) args.push("--model", options.requestedModel);
    args.push(
      "--add-dir",
      "{{PROMPT_DIR}}",
      "--print",
      "Read the complete task brief from {{PROMPT_FILE}} and return the requested answer. Do not quote the brief unless necessary."
    );
    return {
      command: "agy",
      args,
      input: prompt,
      inputMode: "temporary_file"
    };
  }
};
