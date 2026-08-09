import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { adapters } from "../src/adapters/index.js";
import { createServer } from "../src/server.js";

function textResult(result: Awaited<ReturnType<Client["callTool"]>>): unknown {
  if (!("content" in result)) throw new Error("Expected a normal MCP tool result.");
  const content = result.content.find((item) => item.type === "text");
  if (!content || content.type !== "text") throw new Error("Expected text tool content.");
  return JSON.parse(content.text);
}

test("missing LM Studio model returns structured results and panel continues", async () => {
  const previousModel = process.env.LMSTUDIO_MODEL;
  const originalCodexBuildCommand = adapters.codex.buildCommand;
  const testCwd = mkdtempSync(join(tmpdir(), "integrated-agent-server-test-"));
  delete process.env.LMSTUDIO_MODEL;
  adapters.codex.buildCommand = () => ({
    command: process.execPath,
    args: ["-e", "process.stdout.write('PANEL_CODEX_READY')"],
    input: ""
  });

  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const server = createServer();
  const client = new Client({ name: "lmstudio-config-test", version: "1.0.0" });

  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);

    const single = textResult(await client.callTool({
      name: "run_agent",
      arguments: {
        agentId: "lmstudio",
        cwd: testCwd,
        task: "No model configured",
        writePolicy: "read_only",
        timeoutMs: 5_000
      }
    })) as { status: string; errorMessage?: string };
    assert.equal(single.status, "unavailable");
    assert.match(single.errorMessage ?? "", /requires models\.lmstudio or LMSTUDIO_MODEL/);

    const panel = textResult(await client.callTool({
      name: "run_panel",
      arguments: {
        agentIds: ["lmstudio", "codex"],
        cwd: testCwd,
        task: "Continue after LM Studio configuration failure",
        writePolicy: "read_only",
        timeoutMs: 5_000
      }
    })) as { status: string; results: Array<{ agentId: string; status: string; resultText: string }> };
    assert.equal(panel.status, "partial_success");
    assert.deepEqual(panel.results.map((result) => [result.agentId, result.status]), [
      ["lmstudio", "unavailable"],
      ["codex", "ok"]
    ]);
    assert.equal(panel.results[1].resultText, "PANEL_CODEX_READY");
  } finally {
    adapters.codex.buildCommand = originalCodexBuildCommand;
    if (previousModel === undefined) delete process.env.LMSTUDIO_MODEL;
    else process.env.LMSTUDIO_MODEL = previousModel;
    await Promise.allSettled([client.close(), server.close()]);
    rmSync(testCwd, { recursive: true, force: true });
  }
});
