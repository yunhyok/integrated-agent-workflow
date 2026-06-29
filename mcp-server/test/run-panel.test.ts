import assert from "node:assert/strict";
import test from "node:test";
import { summarizePanelStatus } from "../src/tools/run-panel.js";
import { makeAgentResult } from "../src/common/result-schema.js";

test("panel status is partial when at least one result is ok and one failed", () => {
  const status = summarizePanelStatus([
    makeAgentResult({ agentId: "claude", displayName: "Claude Code", status: "ok", durationMs: 1 }),
    makeAgentResult({ agentId: "copilot", displayName: "GitHub Copilot CLI", status: "timeout", durationMs: 1 })
  ]);

  assert.equal(status, "partial_success");
});
