import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

for (const file of ["authentication.md", "doctor.md", "security.md", "usage.md"]) {
  test(`${file} includes plugin identity`, () => {
    const body = readFileSync(resolve(repoRoot, "docs", file), "utf8");
    assert.match(body, /Integrated Agent Workflow v0\.5\.0/);
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
    /Complex, creative, ambiguous, or multi-file tasks are useful signals that multi-agent help may be valuable/,
  );
  assert.match(
    body,
    /Codex may select the orchestration skill automatically only when the user explicitly asks for external agents or when the task is high-risk and independent validation is clearly worth the cost\./,
  );
});

test("usage docs explain direct Codex model selection", () => {
  const body = readFileSync(resolve(repoRoot, "docs/usage.md"), "utf8");
  assert.match(body, /"agentId": "codex"/);
  assert.match(body, /"codex": "gpt-5\.4"/);
  assert.match(body, /does not use GitHub Copilot/);
  assert.match(body, /requestedModel/);
});

test("usage and doctor docs explain registered LM Studio selection", () => {
  const usage = readFileSync(resolve(repoRoot, "docs/usage.md"), "utf8");
  const doctor = readFileSync(resolve(repoRoot, "docs/doctor.md"), "utf8");
  assert.match(usage, /"agentId": "lmstudio"/);
  assert.match(usage, /"lmstudio": "your-loaded-model-id"/);
  assert.match(usage, /list_lmstudio_models/);
  assert.match(usage, /not added to the default `run_panel`/);
  assert.match(usage, /remain `unverified`/);
  assert.match(doctor, /configured-model availability/);
});

test("usage docs route difficult Claude work to exact Opus 5 and explain evidence", () => {
  const body = readFileSync(resolve(repoRoot, "docs/usage.md"), "utf8");
  assert.match(body, /"claude": "claude-opus-5"/);
  assert.match(body, /claude-sonnet-5/);
  assert.match(body, /Do not use the `opus` alias/);
  assert.match(body, /observedModels/);
  assert.match(body, /modelMatch/);
  assert.match(body, /helper models can appear/);
  assert.match(body, /nested delegation bounded/);
});

test("docs cover Antigravity and Windows command discovery without Gemini CLI", () => {
  const usage = readFileSync(resolve(repoRoot, "docs/usage.md"), "utf8");
  const doctor = readFileSync(resolve(repoRoot, "docs/doctor.md"), "utf8");
  const authentication = readFileSync(resolve(repoRoot, "docs/authentication.md"), "utf8");
  assert.match(usage, /"antigravity": "Gemini 3\.1 Pro \(High\)"/);
  assert.doesNotMatch(usage, /"gemini"\s*:/i);
  assert.doesNotMatch(authentication, /Gemini CLI|`gemini`/i);
  assert.match(doctor, /stale PATH/);
});
