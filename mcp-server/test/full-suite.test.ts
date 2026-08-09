import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

test("repository contains all v0.5.0 deliverables", () => {
  const requiredPaths = [
    ".codex-plugin/plugin.json",
    ".mcp.json",
    "README.md",
    "skills/multi-agent-orchestration/SKILL.md",
    "skills/multi-agent-implementation/SKILL.md",
    "skills/multi-agent-review/SKILL.md",
    "mcp-server/src/server.ts",
    "mcp-server/src/adapters/codex.ts",
    "mcp-server/src/adapters/lmstudio.ts",
    "mcp-server/src/common/lmstudio-config.ts",
    "mcp-server/src/tools/lmstudio-models.ts",
    "mcp-server/src/tools/doctor.ts",
    "mcp-server/src/tools/run-agent.ts",
    "mcp-server/src/tools/run-panel.ts",
    "mcp-server/src/tools/summarize-results.ts",
    "docs/authentication.md",
    "docs/doctor.md",
    "docs/security.md",
    "docs/usage.md"
  ];

  for (const requiredPath of requiredPaths) {
    assert.equal(existsSync(resolve(repoRoot, requiredPath)), true, `${requiredPath} should exist`);
  }

  assert.equal(existsSync(resolve(repoRoot, "mcp-server/src/adapters/gemini.ts")), false);
});
