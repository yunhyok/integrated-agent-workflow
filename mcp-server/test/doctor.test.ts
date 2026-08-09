import assert from "node:assert/strict";
import test from "node:test";
import { createDoctorReport } from "../src/tools/doctor.js";

test("doctor reports all agents without secrets", async () => {
  const report = await createDoctorReport({
    cwd: process.cwd(),
    runVersionCheck: false,
    now: new Date("2026-06-29T00:00:00.000Z")
  });

  assert.equal(report.plugin.version, "0.5.0");
  assert.equal(typeof report.workspace.gitRepository, "boolean");
  assert.equal(typeof report.workspace.dirty, "boolean");
  assert.equal(typeof report.workspace.linkedWorktree, "boolean");
  assert.equal(typeof report.workspace.isolatedWriteAvailable, "boolean");
  assert.match(report.doctorCache.path, /doctor\.json$/);
  assert.equal(report.doctorCache.ttlHours, 24);
  assert.deepEqual(report.agents.map((agent) => agent.id).sort(), ["antigravity", "claude", "codex", "copilot", "lmstudio"]);
  for (const agent of report.agents) {
    assert.ok(["unknown", "available", "unavailable"].includes(agent.authStatus));
    assert.ok(["unknown", "not_checked"].includes(agent.dryRunSupported));
  }
  assert.equal(JSON.stringify(report).includes("token"), false);
  assert.equal(JSON.stringify(report).includes("secret"), false);
});

test("doctor does not parse LM Studio configuration when network checks are disabled", async () => {
  const previous = process.env.LMSTUDIO_CONTEXT_WINDOW;
  process.env.LMSTUDIO_CONTEXT_WINDOW = "invalid";
  try {
    const report = await createDoctorReport({
      cwd: process.cwd(),
      runVersionCheck: false,
      now: new Date("2026-06-29T00:00:00.000Z")
    });
    assert.equal(report.agents.length, 5);
  } finally {
    if (previous === undefined) delete process.env.LMSTUDIO_CONTEXT_WINDOW;
    else process.env.LMSTUDIO_CONTEXT_WINDOW = previous;
  }
});
