import { fileURLToPath } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { adapters } from "./adapters/index.js";
import { runProcess } from "./common/process-runner.js";
import { writeRunArtifact } from "./common/run-artifacts.js";
import { evaluateWorkspaceSafety } from "./common/workspace-safety.js";
import type { AgentResult } from "./common/result-schema.js";
import { createDoctorReport } from "./tools/doctor.js";
import { buildAgentPrompt, makeUnsafeWorkspaceResult, normalizeExecutionResult } from "./tools/run-agent.js";
import { summarizePanelStatus } from "./tools/run-panel.js";
import { summarizeResults } from "./tools/summarize-results.js";

export const serverIdentity = {
  name: "integrated-agent-workflow",
  version: "0.1.0"
} as const;

const toolNames = ["doctor", "run_agent", "run_panel", "summarize_results"] as const;
const agentIdSchema = z.enum(["claude", "copilot", "antigravity"]);
const purposeSchema = z.enum(["implementation", "review", "general"]);
const writePolicySchema = z.enum(["read_only", "patch_proposal", "isolated_write"]);

export function listToolNames(): string[] {
  return [...toolNames];
}

export function createServer(): McpServer {
  const server = new McpServer(serverIdentity);

  server.tool("doctor", { cwd: z.string().default(process.cwd()) }, async ({ cwd }) => {
    const report = await createDoctorReport({ cwd, runVersionCheck: true });
    return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }] };
  });

  server.tool(
    "run_agent",
    {
      agentId: agentIdSchema,
      cwd: z.string().default(process.cwd()),
      task: z.string(),
      purpose: purposeSchema.default("general"),
      acceptanceCriteria: z.array(z.string()).default([]),
      writePolicy: writePolicySchema.default("read_only"),
      timeoutMs: z.number().int().positive().default(120000)
    },
    async (input) => {
      const adapter = adapters[input.agentId];
      const safety = evaluateWorkspaceSafety(input.cwd, input.writePolicy);
      if (!safety.allowed) {
        const result = makeUnsafeWorkspaceResult({
          agentId: adapter.id,
          displayName: adapter.displayName,
          reason: safety.reason
        });
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      }

      const prompt = buildAgentPrompt(input);
      const command = adapter.buildCommand(prompt, { timeoutMs: input.timeoutMs });
      const processResult = await runProcess(command.command, command.args, {
        cwd: input.cwd,
        timeoutMs: input.timeoutMs,
        input: command.input
      });
      const logPath = writeRunArtifact(input.cwd, adapter.id, {
        command: command.command,
        args: command.args,
        processResult
      });
      const result = normalizeExecutionResult({
        agentId: adapter.id,
        displayName: adapter.displayName,
        processResult,
        logPath
      });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  );

  server.tool(
    "run_panel",
    {
      agentIds: z.array(agentIdSchema).default(["claude", "copilot", "antigravity"]),
      cwd: z.string().default(process.cwd()),
      task: z.string(),
      purpose: purposeSchema.default("general"),
      acceptanceCriteria: z.array(z.string()).default([]),
      writePolicy: writePolicySchema.default("read_only"),
      timeoutMs: z.number().int().positive().default(120000)
    },
    async (input) => {
      const results: AgentResult[] = [];
      const safety = evaluateWorkspaceSafety(input.cwd, input.writePolicy);
      for (const agentId of input.agentIds) {
        const adapter = adapters[agentId];
        if (!safety.allowed) {
          results.push(
            makeUnsafeWorkspaceResult({
              agentId: adapter.id,
              displayName: adapter.displayName,
              reason: safety.reason
            })
          );
          continue;
        }

        const prompt = buildAgentPrompt(input);
        const command = adapter.buildCommand(prompt, { timeoutMs: input.timeoutMs });
        const processResult = await runProcess(command.command, command.args, {
          cwd: input.cwd,
          timeoutMs: input.timeoutMs,
          input: command.input
        });
        const logPath = writeRunArtifact(input.cwd, adapter.id, {
          command: command.command,
          args: command.args,
          processResult
        });
        results.push(normalizeExecutionResult({ agentId: adapter.id, displayName: adapter.displayName, processResult, logPath }));
      }
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({ status: summarizePanelStatus(results), results }, null, 2)
          }
        ]
      };
    }
  );

  server.tool("summarize_results", { resultsJson: z.string() }, async ({ resultsJson }) => {
    const results = JSON.parse(resultsJson);
    return { content: [{ type: "text", text: JSON.stringify(summarizeResults(results), null, 2) }] };
  });

  return server;
}

if (process.argv.includes("--doctor-smoke")) {
  console.log(`${serverIdentity.name} ${serverIdentity.version} doctor smoke ok`);
} else if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}
