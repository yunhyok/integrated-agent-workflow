import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

test("plugin manifest exposes Integrated Agent Workflow v0.1.0", () => {
  const manifestPath = resolve(repoRoot, ".codex-plugin/plugin.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

  assert.equal(manifest.name, "integrated-agent-workflow");
  assert.equal(manifest.version, "0.1.0");
  assert.equal(manifest.description, "Coordinate Claude, Copilot, and Antigravity CLI agents from Codex.");
  assert.equal(manifest.skills, "./skills");
  assert.equal(manifest.mcpServers.integrated_agent_runner.command, "node");
  assert.deepEqual(manifest.mcpServers.integrated_agent_runner.args, ["./mcp-server/dist/server.js"]);
});

test("README presents plugin name and version", () => {
  const readme = readFileSync(resolve(repoRoot, "README.md"), "utf8");
  assert.match(readme, /^# Integrated Agent Workflow v0\.1\.0/m);
});
