import assert from "node:assert/strict";
import test from "node:test";
import { AGENT_STATUSES, makeAgentResult, pluginIdentity } from "../src/common/result-schema.js";

test("plugin identity is stable", () => {
  assert.deepEqual(pluginIdentity, {
    name: "Integrated Agent Workflow",
    packageName: "integrated-agent-workflow",
    version: "0.5.0"
  });
});

test("agent statuses include expected failure modes", () => {
  assert.deepEqual(AGENT_STATUSES, [
    "ok",
    "unavailable",
    "unauthenticated",
    "timeout",
    "execution_failed",
    "invalid_output",
    "unsafe_request"
  ]);
});

test("makeAgentResult fills common metadata", () => {
  const result = makeAgentResult({
    agentId: "codex",
    displayName: "OpenAI Codex CLI (gpt-5.4)",
    requestedModel: "gpt-5.4",
    observedModels: ["gpt-5.4"],
    modelMatch: "confirmed",
    status: "ok",
    durationMs: 25,
    resultText: "Reviewed the code."
  });

  assert.equal(result.plugin.version, "0.5.0");
  assert.equal(result.agentId, "codex");
  assert.equal(result.displayName, "OpenAI Codex CLI (gpt-5.4)");
  assert.equal(result.requestedModel, "gpt-5.4");
  assert.deepEqual(result.observedModels, ["gpt-5.4"]);
  assert.equal(result.modelMatch, "confirmed");
  assert.equal(result.status, "ok");
  assert.equal(result.resultText, "Reviewed the code.");
  assert.equal(typeof result.createdAt, "string");
});
