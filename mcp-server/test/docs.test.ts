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

test("security docs treat run outputs as sensitive", () => {
  const body = readFileSync(resolve(repoRoot, "docs/security.md"), "utf8");
  assert.match(body, /logs, result files, and run artifacts/);
  assert.match(body, /treated as potentially sensitive/);
});

test("usage docs keep automatic orchestration selection narrow", () => {
  const body = readFileSync(resolve(repoRoot, "docs/usage.md"), "utf8");
  assert.match(
    body,
    /Codex may select the orchestration skill automatically only when the user explicitly asks for external agents or when the task is high-risk and independent validation is clearly worth the cost\./,
  );
});
