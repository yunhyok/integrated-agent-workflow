import assert from "node:assert/strict";
import test from "node:test";
import { adapters } from "../src/adapters/index.js";

test("registers all v0.5.0 adapters", () => {
  assert.deepEqual(Object.keys(adapters).sort(), ["antigravity", "claude", "codex", "copilot", "lmstudio"]);
  assert.equal(adapters.codex.displayName, "OpenAI Codex CLI");
  assert.equal(adapters.lmstudio.displayName, "LM Studio Remote");
  assert.equal(adapters.claude.displayName, "Claude Code");
  assert.equal(adapters.copilot.displayName, "GitHub Copilot CLI");
  assert.equal(adapters.antigravity.displayName, "Google Antigravity CLI");
});

test("adapters build read-only commands", () => {
  const options = { timeoutMs: 1000, writePolicy: "read_only" as const };
  const codex = adapters.codex.buildCommand("Review this.", options);
  const claude = adapters.claude.buildCommand("Review this.", options);
  const copilot = adapters.copilot.buildCommand("Review this.", options);
  const antigravity = adapters.antigravity.buildCommand("Review this.", options);

  assert.equal(codex.command, "codex");
  assert.deepEqual(codex.args.slice(0, 12), [
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
    "read-only"
  ]);
  assert.equal(codex.args.at(-1), "-");
  assert.equal(codex.args.includes("Review this."), false);
  assert.equal(codex.input, "Review this.");

  assert.equal(claude.command, "claude");
  assert.deepEqual(claude.args.slice(0, 2), ["--permission-mode", "plan"]);
  assert.deepEqual(claude.args.slice(2, 4), ["--output-format", "json"]);
  assert.ok(claude.args.includes("--no-session-persistence"));
  assert.ok(claude.args.includes("-p"));
  assert.equal(claude.args.includes("Review this."), false);
  assert.equal(claude.input, "Review this.");

  assert.equal(copilot.command, "copilot");
  assert.ok(copilot.args.includes("--plan"));
  assert.equal(copilot.args.includes("--prompt"), false);
  assert.equal(copilot.args.includes("Review this."), false);
  assert.equal(copilot.input, "Review this.");

  assert.equal(antigravity.command, "agy");
  assert.deepEqual(antigravity.args.slice(0, 2), ["--mode", "plan"]);
  assert.ok(antigravity.args.includes("--print"));
  assert.equal(antigravity.args.includes("Review this."), false);
  assert.equal(antigravity.input, "Review this.");
  assert.equal(antigravity.inputMode, "temporary_file");
});

test("adapters pass requested models through provider-specific flags", () => {
  const options = { timeoutMs: 1000, writePolicy: "read_only" as const };
  const codex = adapters.codex.buildCommand("Review this.", { ...options, requestedModel: "gpt-5.4" });
  const claude = adapters.claude.buildCommand("Review this.", {
    ...options,
    requestedModel: "claude-opus-5"
  });
  const copilot = adapters.copilot.buildCommand("Review this.", {
    ...options,
    requestedModel: "gpt-5.3-codex"
  });
  const antigravity = adapters.antigravity.buildCommand("Review this.", {
    ...options,
    requestedModel: "Gemini 3.1 Pro (High)"
  });

  assert.deepEqual(codex.args.slice(-3), ["--model", "gpt-5.4", "-"]);
  assert.deepEqual(claude.args.slice(-3), ["--model", "claude-opus-5", "-p"]);
  assert.deepEqual(copilot.args.slice(-2), ["--model", "gpt-5.3-codex"]);
  assert.deepEqual(antigravity.args.slice(2, 4), ["--model", "Gemini 3.1 Pro (High)"]);
  assert.ok(antigravity.args.includes("{{PROMPT_FILE}}") || antigravity.args.at(-1)?.includes("{{PROMPT_FILE}}"));
});

test("LM Studio uses an isolated custom Responses provider for the configured remote endpoint", () => {
  const command = adapters.lmstudio.buildCommand("Review locally.", {
    timeoutMs: 1000,
    writePolicy: "read_only",
    requestedModel: "local-model-id",
    providerBaseUrl: "http://127.0.0.1:1234/v1",
    modelContextWindow: 32768
  });

  assert.equal(command.command, "codex");
  assert.equal(command.args.includes("Review locally."), false);
  assert.equal(command.input, "Review locally.");
  assert.ok(command.args.includes('model_provider="lmstudio_remote"'));
  assert.ok(command.args.includes('model_providers.lmstudio_remote.name="LM Studio Remote"'));
  assert.ok(command.args.includes('model_providers.lmstudio_remote.base_url="http://127.0.0.1:1234/v1"'));
  assert.ok(command.args.includes('model_providers.lmstudio_remote.wire_api="responses"'));
  assert.ok(command.args.includes("model_context_window=32768"));
  assert.deepEqual(command.args.slice(-3), ["--model", "local-model-id", "-"]);
  const sandboxIndex = command.args.indexOf("--sandbox");
  assert.equal(command.args[sandboxIndex + 1], "read-only");
});

test("Codex grants workspace-write only for isolated_write", () => {
  const command = adapters.codex.buildCommand("Implement this.", {
    timeoutMs: 1000,
    writePolicy: "isolated_write"
  });

  const sandboxIndex = command.args.indexOf("--sandbox");
  assert.equal(command.args[sandboxIndex + 1], "workspace-write");
});

test("LM Studio grants workspace-write only for isolated_write", () => {
  const command = adapters.lmstudio.buildCommand("Implement this.", {
    timeoutMs: 1000,
    writePolicy: "isolated_write",
    requestedModel: "local-model-id",
    providerBaseUrl: "http://127.0.0.1:1234/v1"
  });

  const sandboxIndex = command.args.indexOf("--sandbox");
  assert.equal(command.args[sandboxIndex + 1], "workspace-write");
});

test("external adapters only enable write-oriented modes for isolated_write", () => {
  const options = { timeoutMs: 1000, writePolicy: "isolated_write" as const };
  assert.deepEqual(adapters.claude.buildCommand("Implement.", options).args.slice(0, 2), [
    "--permission-mode",
    "acceptEdits"
  ]);
  assert.equal(adapters.copilot.buildCommand("Implement.", options).args.includes("--plan"), false);
  assert.equal(adapters.copilot.buildCommand("Implement.", options).args.includes("--allow-all-tools"), true);
  assert.deepEqual(adapters.antigravity.buildCommand("Implement.", options).args.slice(0, 2), [
    "--mode",
    "accept-edits"
  ]);
});
