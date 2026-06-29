import assert from "node:assert/strict";
import test from "node:test";
import { buildAgentPrompt, makeUnsafeWorkspaceResult, normalizeExecutionResult } from "../src/tools/run-agent.js";

test("buildAgentPrompt includes acceptance criteria and safety policy", () => {
  const prompt = buildAgentPrompt({
    task: "Review the plugin manifest.",
    purpose: "review",
    acceptanceCriteria: ["Find correctness issues.", "Do not modify files."],
    writePolicy: "read_only"
  });

  assert.match(prompt, /Review the plugin manifest/);
  assert.match(prompt, /Find correctness issues/);
  assert.match(prompt, /Do not modify files/);
  assert.match(prompt, /write policy: read_only/);
});

test("buildAgentPrompt redacts secrets from task and acceptance criteria", () => {
  const prompt = buildAgentPrompt({
    task: "Review this token sk-test12345 and API_KEY=abc123.",
    purpose: "review",
    acceptanceCriteria: ["Do not leak password: hunter2."],
    writePolicy: "read_only"
  });

  assert.equal(prompt.includes("sk-test12345"), false);
  assert.equal(prompt.includes("API_KEY=abc123"), false);
  assert.equal(prompt.includes("password: hunter2"), false);
  assert.match(prompt, /\[REDACTED\]/);
});

test("normalizeExecutionResult maps auth-looking failures to unauthenticated", () => {
  const result = normalizeExecutionResult({
    agentId: "claude",
    displayName: "Claude Code",
    processResult: {
      status: "execution_failed",
      exitCode: 1,
      stdout: "",
      stderr: "not logged in",
      durationMs: 10
    }
  });

  assert.equal(result.status, "unauthenticated");
  assert.equal(result.stderrSummary, "not logged in");
});

test("makeUnsafeWorkspaceResult returns unsafe_request without execution details", () => {
  const result = makeUnsafeWorkspaceResult({
    agentId: "copilot",
    displayName: "GitHub Copilot CLI",
    reason: "isolated_write requires an isolated linked worktree"
  });

  assert.equal(result.status, "unsafe_request");
  assert.equal(result.durationMs, 0);
  assert.equal(result.errorMessage, "isolated_write requires an isolated linked worktree");
  assert.equal(result.stdout, undefined);
});
