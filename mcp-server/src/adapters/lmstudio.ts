import { LMSTUDIO_PROVIDER_ID } from "../common/lmstudio-config.js";
import type { CliAdapter } from "./types.js";

function tomlString(value: string): string {
  return JSON.stringify(value);
}

export const lmstudioAdapter: CliAdapter = {
  id: "lmstudio",
  displayName: "LM Studio Remote",
  binaryName: "codex",
  versionArgs: ["--version"],
  authHint: "Start the configured LM Studio server, load the selected model, then rerun doctor.",
  buildCommand(prompt, options) {
    if (!options.requestedModel) {
      throw new Error("LM Studio requires models.lmstudio or LMSTUDIO_MODEL.");
    }
    if (!options.providerBaseUrl) {
      throw new Error("LM Studio requires a configured provider base URL.");
    }

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
      sandbox,
      "-c",
      `model_provider=${tomlString(LMSTUDIO_PROVIDER_ID)}`,
      "-c",
      `model_providers.${LMSTUDIO_PROVIDER_ID}.name=${tomlString("LM Studio Remote")}`,
      "-c",
      `model_providers.${LMSTUDIO_PROVIDER_ID}.base_url=${tomlString(options.providerBaseUrl)}`,
      "-c",
      `model_providers.${LMSTUDIO_PROVIDER_ID}.wire_api=${tomlString("responses")}`
    ];

    if (options.providerApiKeyEnvName) {
      args.push(
        "-c",
        `model_providers.${LMSTUDIO_PROVIDER_ID}.env_key=${tomlString(options.providerApiKeyEnvName)}`
      );
    }

    if (options.modelContextWindow) {
      args.push("-c", `model_context_window=${options.modelContextWindow}`);
    }

    args.push("--model", options.requestedModel, "-");
    return {
      command: "codex",
      args,
      input: prompt
    };
  }
};
