import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

function readSkill(name: string): string {
  return readFileSync(resolve(repoRoot, "skills", name, "SKILL.md"), "utf8");
}

test("orchestration skill narrows external CLI auto-use criteria", () => {
  const body = readSkill("multi-agent-orchestration");
  const frontmatter = body.match(/^---\n(?<frontmatter>[\s\S]*?)\n---/);
  assert.ok(frontmatter?.groups);
  const description = frontmatter.groups.frontmatter.match(/^description: (?<description>.*)$/m);
  assert.ok(description?.groups);

  assert.match(frontmatter.groups.frontmatter, /^name: multi-agent-orchestration$/m);
  assert.ok(description.groups.description.includes("Claude, Copilot, Antigravity"));
  assert.ok(description.groups.description.includes("independent review"));
  assert.doesNotMatch(
    description.groups.description,
    /complex, high-risk, creative, ambiguous, spans multiple files/,
  );
  assert.ok(
    body.includes(
      "Do not run external CLIs just because a task is merely complex, creative, ambiguous, or spans multiple files.",
    ),
  );
  assert.ok(
    body.includes(
      "Run external CLIs automatically only when the user explicitly asks for them or when the task is high-risk and independent validation is clearly worth the cost.",
    ),
  );
  assert.ok(
    body.includes("Ask for confirmation before any long-running, write-capable, or broad external execution."),
  );
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
