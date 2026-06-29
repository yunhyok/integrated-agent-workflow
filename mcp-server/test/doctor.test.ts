import assert from "node:assert/strict";
import test from "node:test";
import { createDoctorReport } from "../src/tools/doctor.js";

test("doctor reports all agents without secrets", async () => {
  const report = await createDoctorReport({
    cwd: process.cwd(),
    runVersionCheck: false,
    now: new Date("2026-06-29T00:00:00.000Z")
  });

  assert.equal(report.plugin.version, "0.1.0");
  assert.deepEqual(report.agents.map((agent) => agent.id).sort(), ["antigravity", "claude", "copilot"]);
  assert.equal(JSON.stringify(report).includes("token"), false);
  assert.equal(JSON.stringify(report).includes("secret"), false);
});
