import type { CliAdapter } from "./types.js";

export const codexAdapter: CliAdapter = {
  id: "codex",
  displayName: "OpenAI Codex CLI",
  binaryName: "codex",
  versionArgs: ["--version"],
  authHint: "Run `codex login`, then rerun doctor.",
  buildCommand(prompt, options) {
    const sandbox = options.writePolicy === "isolated_write" ? "workspace-write" : "read-only";
    const args = [
      "exec",
      "--ephemeral",
      "--ignore-user-config",
      "--disable",
      "plugins",
      "--disable",
      "multi_agent",
      "--skip-git-repo-check",
      "--color",
      "never",
      "--sandbox",
      sandbox
    ];

    if (options.requestedModel) {
      args.push("--model", options.requestedModel);
    }

    args.push("-");
    return {
      command: "codex",
      args,
      input: prompt
    };
  }
};
