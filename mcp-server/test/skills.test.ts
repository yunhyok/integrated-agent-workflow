import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

function readSkill(name: string): string {
  return readFileSync(resolve(repoRoot, "skills", name, "SKILL.md"), "utf8");
}

test("orchestration skill advertises automatic complex task selection", () => {
  const body = readSkill("multi-agent-orchestration");
  assert.match(body, /^---\nname: multi-agent-orchestration/m);
  assert.match(body, /complex, high-risk, creative, ambiguous/m);
  assert.match(body, /Claude, Copilot, Antigravity/m);
  assert.match(body, /Codex remains the final verifier/m);
});

test("implementation and review presets defer to orchestration", () => {
  const implementation = readSkill("multi-agent-implementation");
  const review = readSkill("multi-agent-review");
  assert.match(implementation, /Load multi-agent-orchestration first/m);
  assert.match(implementation, /implementation brief/m);
  assert.match(review, /Load multi-agent-orchestration first/m);
  assert.match(review, /review brief/m);
});
