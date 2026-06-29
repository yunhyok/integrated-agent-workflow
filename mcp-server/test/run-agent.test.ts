import assert from "node:assert/strict";
import test from "node:test";
import { buildAgentPrompt, normalizeExecutionResult } from "../src/tools/run-agent.js";

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

test("normalizeExecutionResult maps non-zero exit to execution_failed", () => {
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

  assert.equal(result.status, "execution_failed");
  assert.equal(result.stderrSummary, "not logged in");
});
