import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

test("plugin manifest exposes Integrated Agent Workflow v0.5.0", () => {
  const manifestPath = resolve(repoRoot, ".codex-plugin/plugin.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

  assert.equal(manifest.name, "integrated-agent-workflow");
  assert.equal(manifest.version, "0.5.0");
  assert.equal(manifest.description, "Coordinate OpenAI Codex, LM Studio, Claude, Copilot, and Antigravity agents from Codex.");
  assert.equal(typeof manifest.author, "object");
  assert.notEqual(manifest.author, null);
  assert.equal(typeof manifest.interface, "object");
  assert.notEqual(manifest.interface, null);
  assert.equal(manifest.interface.displayName, "Integrated Agent Workflow v0.5.0");
  assert.doesNotMatch(manifest.interface.longDescription, /Gemini CLI/i);
  assert.equal(manifest.skills, "./skills");
  assert.equal(manifest.mcpServers, "./.mcp.json");
  const mcpConfig = JSON.parse(readFileSync(resolve(repoRoot, ".mcp.json"), "utf8"));
  assert.equal(mcpConfig.mcpServers.integrated_agent_runner.command, "node");
  assert.deepEqual(mcpConfig.mcpServers.integrated_agent_runner.args, ["./mcp-server/dist/server.js"]);
  assert.equal(mcpConfig.mcpServers.integrated_agent_runner.cwd, ".");
  assert.equal(mcpConfig.mcpServers.integrated_agent_runner.env, undefined);
  assert.equal(mcpConfig.mcpServers.integrated_agent_runner.tool_timeout_sec, 660);
  assert.equal(existsSync(resolve(repoRoot, "mcp-server/src/server.ts")), true);
  assert.equal(existsSync(resolve(repoRoot, "mcp-server/package-lock.json")), true);
});

test("README presents plugin name and version", () => {
  const readme = readFileSync(resolve(repoRoot, "README.md"), "utf8");
  assert.match(readme, /^# Integrated Agent Workflow v0\.5\.0/m);
  assert.match(readme, /LM Studio/);
  assert.doesNotMatch(readme, /Gemini CLI/i);
});
