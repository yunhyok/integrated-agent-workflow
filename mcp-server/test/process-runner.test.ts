import assert from "node:assert/strict";
import test from "node:test";
import { runProcess } from "../src/common/process-runner.js";

test("captures stdout and exit code", async () => {
  const result = await runProcess(process.execPath, ["-e", "console.log('hello')"], {
    cwd: process.cwd(),
    timeoutMs: 5_000
  });

  assert.equal(result.status, "ok");
  assert.equal(result.exitCode, 0);
  assert.match(result.stdout, /hello/);
});

test("marks timeout", async () => {
  const result = await runProcess(process.execPath, ["-e", "setTimeout(() => {}, 10000)"], {
    cwd: process.cwd(),
    timeoutMs: 50
  });

  assert.equal(result.status, "timeout");
});
