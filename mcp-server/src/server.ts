import { fileURLToPath } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { adapters } from "./adapters/index.js";
import { getLMStudioConfig } from "./common/lmstudio-config.js";
import { runProcess } from "./common/process-runner.js";
import { writeRunArtifact } from "./common/run-artifacts.js";
import { evaluateWorkspaceSafety } from "./common/workspace-safety.js";
import { makeAgentResult, type AgentResult } from "./common/result-schema.js";
import { createDoctorReport } from "./tools/doctor.js";
import { listLMStudioModels } from "./tools/lmstudio-models.js";
import { buildAgentPrompt, makeUnsafeWorkspaceResult, normalizeExecutionResult } from "./tools/run-agent.js";
import { summarizePanelStatus } from "./tools/run-panel.js";
import { summarizeResults } from "./tools/summarize-results.js";

export const serverIdentity = {
  name: "integrated-agent-workflow",
  version: "0.5.0"
} as const;

const toolNames = ["doctor", "list_lmstudio_models", "run_agent", "run_panel", "summarize_results"] as const;
const agentIdSchema = z.enum(["codex", "lmstudio", "claude", "copilot", "antigravity"]);
const purposeSchema = z.enum(["implementation", "review", "general"]);
const writePolicySchema = z.enum(["read_only", "patch_proposal", "isolated_write"]);
const modelMapSchema = z
  .object({
    codex: z.string().min(1).optional(),
    lmstudio: z.string().min(1).optional(),
    claude: z.string().min(1).optional(),
    copilot: z.string().min(1).optional(),
    antigravity: z.string().min(1).optional()
  })
  .default({});

function makeDisplayName(baseName: string, requestedModel?: string): string {
  return requestedModel ? `${baseName} (${requestedModel})` : baseName;
}

function configuredLMStudioModel(): string | undefined {
  return process.env.LMSTUDIO_MODEL?.trim() || undefined;
}

function makeLMStudioConfigurationResult(requestedModel: string | undefined, error: unknown): AgentResult {
  const message = error instanceof Error ? error.message : String(error);
  return makeAgentResult({
    agentId: "lmstudio",
    displayName: makeDisplayName(adapters.lmstudio.displayName, requestedModel),
    requestedModel,
    status: "unavailable",
    durationMs: 0,
    errorMessage: `Invalid LM Studio configuration: ${message.slice(0, 500)}`
  });
}

export function listToolNames(): string[] {
  return [...toolNames];
}

export function createServer(): McpServer {
  const server = new McpServer(serverIdentity);

  server.tool("doctor", { cwd: z.string().default(process.cwd()) }, async ({ cwd }) => {
    const report = await createDoctorReport({ cwd, runVersionCheck: true });
    return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }] };
  });

  server.tool("list_lmstudio_models", {}, async () => {
    const result = await listLMStudioModels();
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  });

  server.tool(
    "run_agent",
    {
      agentId: agentIdSchema,
      cwd: z.string().default(process.cwd()),
      task: z.string(),
      purpose: purposeSchema.default("general"),
      acceptanceCriteria: z.array(z.string()).default([]),
      models: modelMapSchema,
      writePolicy: writePolicySchema.default("read_only"),
      timeoutMs: z.number().int().positive().default(120000)
    },
    async (input) => {
      const adapter = adapters[input.agentId];
      const requestedModel = input.models[input.agentId] ?? (input.agentId === "lmstudio" ? configuredLMStudioModel() : undefined);
      const displayName = makeDisplayName(adapter.displayName, requestedModel);
      const safety = evaluateWorkspaceSafety(input.cwd, input.writePolicy);
      if (!safety.allowed) {
        const result = makeUnsafeWorkspaceResult({
          agentId: adapter.id,
          displayName,
          requestedModel,
          reason: safety.reason
        });
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      }

      let lmStudioConfig;
      if (input.agentId === "lmstudio") {
        try {
          lmStudioConfig = getLMStudioConfig();
        } catch (error) {
          const result = makeLMStudioConfigurationResult(requestedModel, error);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
        }
        if (!requestedModel) {
          const result = makeLMStudioConfigurationResult(
            requestedModel,
            new Error("LM Studio requires models.lmstudio or LMSTUDIO_MODEL.")
          );
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
        }
      }

      const prompt = buildAgentPrompt(input);
      const command = adapter.buildCommand(prompt, {
        timeoutMs: input.timeoutMs,
        requestedModel,
        writePolicy: input.writePolicy,
        providerBaseUrl: lmStudioConfig?.openAIBaseUrl,
        providerApiKeyEnvName: lmStudioConfig?.apiToken ? "LMSTUDIO_API_TOKEN" : undefined,
        modelContextWindow: lmStudioConfig?.contextWindow
      });
      const processResult = await runProcess(command.command, command.args, {
        cwd: input.cwd,
        timeoutMs: input.timeoutMs,
        input: command.input,
        inputMode: command.inputMode
      });
      const logPath = writeRunArtifact(input.cwd, adapter.id, {
        displayName,
        requestedModel,
        command: command.command,
        args: command.args,
        processResult
      });
      const result = normalizeExecutionResult({
        agentId: adapter.id,
        displayName,
        requestedModel,
        processResult,
        logPath
      });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  );

  server.tool(
    "run_panel",
    {
      agentIds: z.array(agentIdSchema).default(["codex", "claude", "copilot", "antigravity"]),
      cwd: z.string().default(process.cwd()),
      task: z.string(),
      purpose: purposeSchema.default("general"),
      acceptanceCriteria: z.array(z.string()).default([]),
      models: modelMapSchema,
      writePolicy: writePolicySchema.default("read_only"),
      timeoutMs: z.number().int().positive().default(120000)
    },
    async (input) => {
      const results: AgentResult[] = [];
      const safety = evaluateWorkspaceSafety(input.cwd, input.writePolicy);
      for (const agentId of input.agentIds) {
        const adapter = adapters[agentId];
        const requestedModel = input.models[agentId] ?? (agentId === "lmstudio" ? configuredLMStudioModel() : undefined);
        const displayName = makeDisplayName(adapter.displayName, requestedModel);
        if (!safety.allowed) {
          results.push(
            makeUnsafeWorkspaceResult({
              agentId: adapter.id,
              displayName,
              requestedModel,
              reason: safety.reason
            })
          );
          continue;
        }

        let lmStudioConfig;
        if (agentId === "lmstudio") {
          try {
            lmStudioConfig = getLMStudioConfig();
          } catch (error) {
            results.push(makeLMStudioConfigurationResult(requestedModel, error));
            continue;
          }
          if (!requestedModel) {
            results.push(makeLMStudioConfigurationResult(
              requestedModel,
              new Error("LM Studio requires models.lmstudio or LMSTUDIO_MODEL.")
            ));
            continue;
          }
        }

        const prompt = buildAgentPrompt(input);
        const command = adapter.buildCommand(prompt, {
          timeoutMs: input.timeoutMs,
          requestedModel,
          writePolicy: input.writePolicy,
          providerBaseUrl: lmStudioConfig?.openAIBaseUrl,
          providerApiKeyEnvName: lmStudioConfig?.apiToken ? "LMSTUDIO_API_TOKEN" : undefined,
          modelContextWindow: lmStudioConfig?.contextWindow
        });
        const processResult = await runProcess(command.command, command.args, {
          cwd: input.cwd,
          timeoutMs: input.timeoutMs,
          input: command.input,
          inputMode: command.inputMode
        });
        const logPath = writeRunArtifact(input.cwd, adapter.id, {
          displayName,
          requestedModel,
          command: command.command,
          args: command.args,
          processResult
        });
        results.push(normalizeExecutionResult({
          agentId: adapter.id,
          displayName,
          requestedModel,
          processResult,
          logPath
        }));
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
