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
  const frontmatter = body.match(/^---\r?\n(?<frontmatter>[\s\S]*?)\r?\n---(?:\r?\n|$)/);
  assert.ok(frontmatter?.groups);
  const description = frontmatter.groups.frontmatter.match(/^description: (?<description>.*)$/m);
  assert.ok(description?.groups);

  assert.match(frontmatter.groups.frontmatter, /^name: multi-agent-orchestration$/m);
  assert.ok(description.groups.description.includes("OpenAI Codex, GPT, LM Studio, Claude, Copilot, Antigravity"));
  assert.equal(description.groups.description.includes("Gemini"), false);
  assert.ok(description.groups.description.includes("independent review"));
  assert.doesNotMatch(
    description.groups.description,
    /complex, high-risk, creative, ambiguous, spans multiple files/,
  );
  assert.ok(
    body.includes(
      "Complex, creative, ambiguous, or multi-file tasks are useful signals that multi-agent help may be valuable.",
    ),
  );
  assert.ok(
    body.includes(
      "Those signals alone do not permit automatic external CLI execution.",
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
  assert.match(body, /timeout above 600000 ms as long-running/);
  assert.match(body, /read-only agent run at or below 600000 ms by default/);
  assert.match(body, /Codex remains the final verifier/m);
  assert.match(body, /models.*`codex`.*`lmstudio`.*`claude`.*`copilot`.*`antigravity`/m);
  assert.match(body, /call `list_lmstudio_models`/);
  assert.match(body, /LM Studio results remain `unverified`/);
  assert.match(body, /`models\.claude` to the exact ID `claude-opus-5`/);
  assert.match(body, /`claude-sonnet-5`/);
  assert.match(body, /Never use the `opus` alias/);
  assert.match(body, /small explicit cap/);
  assert.match(body, /`observedModels` and `modelMatch`/);
  assert.doesNotMatch(body, /agent ID `gemini`|Google Gemini CLI|`gemini`,/m);
});

test("implementation and review presets defer to orchestration", () => {
  const implementation = readSkill("multi-agent-implementation");
  const review = readSkill("multi-agent-review");
  assert.match(implementation, /Load multi-agent-orchestration first/m);
  assert.match(implementation, /implementation brief/m);
  assert.match(review, /Load multi-agent-orchestration first/m);
  assert.match(review, /review brief/m);
});
