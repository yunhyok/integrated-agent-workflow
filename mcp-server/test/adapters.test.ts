import assert from "node:assert/strict";
import test from "node:test";
import { adapters } from "../src/adapters/index.js";

test("registers all v1 adapters", () => {
  assert.deepEqual(Object.keys(adapters).sort(), ["antigravity", "claude", "copilot"]);
  assert.equal(adapters.claude.displayName, "Claude Code");
  assert.equal(adapters.copilot.displayName, "GitHub Copilot CLI");
  assert.equal(adapters.antigravity.displayName, "Google Antigravity CLI");
});

test("adapters build read-only commands", () => {
  const claude = adapters.claude.buildCommand("Review this.", { timeoutMs: 1000 });
  const copilot = adapters.copilot.buildCommand("Review this.", { timeoutMs: 1000 });
  const antigravity = adapters.antigravity.buildCommand("Review this.", { timeoutMs: 1000 });

  assert.equal(claude.command, "claude");
  assert.deepEqual(claude.args.slice(0, 1), ["-p"]);
  assert.equal(claude.args.includes("Review this."), false);
  assert.equal(claude.input, "Review this.");

  assert.equal(copilot.command, "copilot");
  assert.ok(copilot.args.includes("--prompt") || copilot.args.includes("-p"));
  assert.equal(copilot.args.includes("Review this."), false);
  assert.equal(copilot.input, "Review this.");

  assert.equal(antigravity.command, "agy");
  assert.ok(antigravity.args.includes("--prompt") || antigravity.args.includes("-p"));
  assert.equal(antigravity.args.includes("Review this."), false);
  assert.equal(antigravity.input, "Review this.");
});
