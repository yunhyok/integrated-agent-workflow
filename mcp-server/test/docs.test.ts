import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

for (const file of ["authentication.md", "doctor.md", "security.md", "usage.md"]) {
  test(`${file} includes plugin identity`, () => {
    const body = readFileSync(resolve(repoRoot, "docs", file), "utf8");
    assert.match(body, /Integrated Agent Workflow v0\.1\.0/);
  });
}

test("authentication docs explain one-time login model", () => {
  const body = readFileSync(resolve(repoRoot, "docs/authentication.md"), "utf8");
  assert.match(body, /not authenticate on every run/);
  assert.match(body, /does not store tokens/);
});
