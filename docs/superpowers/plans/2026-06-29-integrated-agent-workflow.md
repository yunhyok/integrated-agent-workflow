# Integrated Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Integrated Agent Workflow v0.1.0 as a Codex plugin that can orchestrate Claude Code, GitHub Copilot CLI, and Google Antigravity CLI through a local MCP server.

**Architecture:** The plugin contains three Codex skills for workflow policy and a TypeScript MCP server for local CLI execution. Skills decide when and how to use multi-agent execution; MCP tools perform doctor checks, run individual agents, run panels, and normalize summaries.

**Tech Stack:** Codex plugin manifest, Markdown skills/docs, Node.js 20+, TypeScript, `@modelcontextprotocol/sdk`, `node:test`, gitignored local run/cache artifacts.

---

## File Structure

- Create `.codex-plugin/plugin.json`: plugin identity, version, skills path, and MCP server entry.
- Create `.gitignore`: ignore local multi-agent caches, run logs, build outputs, and dependencies.
- Create `README.md`: user-facing plugin name/version and quick start.
- Create `skills/multi-agent-orchestration/SKILL.md`: automatic selection and shared orchestration workflow.
- Create `skills/multi-agent-implementation/SKILL.md`: implementation preset.
- Create `skills/multi-agent-review/SKILL.md`: review preset.
- Create `mcp-server/package.json`: TypeScript build/test scripts and dependencies.
- Create `mcp-server/tsconfig.json`: compiler settings.
- Create `mcp-server/src/server.ts`: MCP stdio server and tool registration.
- Create `mcp-server/src/common/result-schema.ts`: shared result types and status helpers.
- Create `mcp-server/src/common/process-runner.ts`: spawn wrapper with timeout and captured output.
- Create `mcp-server/src/common/redaction.ts`: secret redaction helpers.
- Create `mcp-server/src/common/workspace-safety.ts`: git/workspace checks and write policy decisions.
- Create `mcp-server/src/adapters/types.ts`: adapter interface.
- Create `mcp-server/src/adapters/claude.ts`: Claude Code CLI adapter.
- Create `mcp-server/src/adapters/copilot.ts`: GitHub Copilot CLI adapter.
- Create `mcp-server/src/adapters/antigravity.ts`: Antigravity CLI adapter.
- Create `mcp-server/src/adapters/index.ts`: adapter registry.
- Create `mcp-server/src/tools/doctor.ts`: doctor tool implementation and non-secret cache.
- Create `mcp-server/src/tools/run-agent.ts`: single-agent execution tool.
- Create `mcp-server/src/tools/run-panel.ts`: multi-agent execution tool.
- Create `mcp-server/src/tools/summarize-results.ts`: result grouping helper.
- Create `mcp-server/test/*.test.ts`: unit tests for manifest, skills, schema, redaction, runner, adapters, and tools.
- Create `docs/authentication.md`: first-time and expired-session login guidance.
- Create `docs/doctor.md`: doctor output and troubleshooting.
- Create `docs/security.md`: secrets, logs, and write isolation.
- Create `docs/usage.md`: implementation and review examples.

### Task 1: Plugin Scaffold And Identity

**Files:**
- Create: `.codex-plugin/plugin.json`
- Create: `.gitignore`
- Create: `README.md`
- Create: `mcp-server/package.json`
- Create: `mcp-server/tsconfig.json`
- Create: `mcp-server/test/plugin-manifest.test.ts`

- [ ] **Step 1: Write the failing manifest test**

Create `mcp-server/test/plugin-manifest.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "plugin manifest"
```

Expected: failure because `package.json`, `.codex-plugin/plugin.json`, and `README.md` do not exist yet.

- [ ] **Step 3: Create package and TypeScript config**

Create `mcp-server/package.json`:

```json
{
  "name": "integrated-agent-workflow-mcp",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "description": "Local MCP server for Integrated Agent Workflow.",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "node --test --import tsx ./test/*.test.ts",
    "doctor": "tsx src/server.ts --doctor-smoke"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  },
  "devDependencies": {
    "@types/node": "^20.14.0",
    "tsx": "^4.19.0",
    "typescript": "^5.5.0"
  },
  "engines": {
    "node": ">=20"
  }
}
```

Create `mcp-server/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 4: Create plugin manifest, gitignore, and README**

Create `.codex-plugin/plugin.json`:

```json
{
  "name": "integrated-agent-workflow",
  "version": "0.1.0",
  "description": "Coordinate Claude, Copilot, and Antigravity CLI agents from Codex.",
  "skills": "./skills",
  "mcpServers": {
    "integrated_agent_runner": {
      "command": "node",
      "args": ["./mcp-server/dist/server.js"],
      "startup_timeout_sec": 10,
      "tool_timeout_sec": 300
    }
  }
}
```

Create `.gitignore`:

```gitignore
node_modules/
dist/
.codex/multi-agent/cache/
.codex/multi-agent/runs/
npm-debug.log*
```

Create `README.md`:

```md
# Integrated Agent Workflow v0.1.0

Integrated Agent Workflow is a Codex plugin that lets Codex coordinate Claude Code, GitHub Copilot CLI, and Google Antigravity CLI through a local MCP server.

Codex remains the orchestrator and verifier. External agent output is advisory until Codex checks the final result.

## Quick Start

1. Install and authenticate the external CLIs you want to use.
2. Build the MCP server with `npm --prefix mcp-server install` and `npm --prefix mcp-server run build`.
3. Install or enable this plugin in Codex.
4. Ask Codex to use multi-agent review or implementation when a task is complex, risky, or benefits from independent opinions.

## Version

Integrated Agent Workflow v0.1.0
```

- [ ] **Step 5: Install dependencies and verify the test passes**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm install
npm test -- --test-name-pattern "plugin manifest"
```

Expected: PASS for both manifest identity assertions.

- [ ] **Step 6: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add .codex-plugin/plugin.json .gitignore README.md mcp-server/package.json mcp-server/tsconfig.json mcp-server/test/plugin-manifest.test.ts
git commit -m "feat: scaffold integrated agent plugin"
```

### Task 2: Skill Package

**Files:**
- Create: `skills/multi-agent-orchestration/SKILL.md`
- Create: `skills/multi-agent-implementation/SKILL.md`
- Create: `skills/multi-agent-review/SKILL.md`
- Create: `mcp-server/test/skills.test.ts`

- [ ] **Step 1: Write the failing skill metadata test**

Create `mcp-server/test/skills.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "skill"
```

Expected: failure because skill files do not exist.

- [ ] **Step 3: Create the orchestration skill**

Create `skills/multi-agent-orchestration/SKILL.md`:

```md
---
name: multi-agent-orchestration
description: Use when a task is complex, high-risk, creative, ambiguous, spans multiple files, benefits from independent review, or mentions Claude, Copilot, Antigravity, external CLI agents, validation diversity, or multi-agent execution.
---

# Multi-Agent Orchestration

Codex is the coordinator and Codex remains the final verifier. External agent output is advisory until Codex checks the evidence, final diff, and relevant tests.

## Entry Decision

Use this workflow when one or more are true:

- The task spans multiple files, modules, workflows, or design decisions.
- The task is high-risk because it touches release, security, data loss, authentication, payments, or broad refactors.
- The user asks for independent validation, multiple agents, Claude, Copilot, Antigravity, or diverse proposals.
- The task is creative or ambiguous enough that multiple independent answers can improve the result.

Skip external CLI execution when all are true:

- The task is a small direct edit, typo fix, or simple command.
- Independent review would add little evidence.
- No external CLI is available and the task can be completed directly.

Before a long-running, write-capable, or broad execution, summarize the proposed agent panel and ask for confirmation.

## Workflow

1. Restate the task, constraints, and acceptance criteria.
2. Select the preset: implementation, review, or general.
3. Call `doctor` on the integrated agent runner MCP server.
4. Choose available agents from Claude, Copilot, and Antigravity.
5. Build one concise brief per agent with identical acceptance criteria.
6. Prefer read-only or patch-proposal mode unless isolated write execution is explicitly safe.
7. Call `run_panel` for independent execution or `run_agent` for one target.
8. Compare returned results for agreement, conflicts, missing evidence, and risky assumptions.
9. Verify the final answer through direct Codex inspection, tests, or command output.
10. Report which external agents contributed usable output and which failed.

## Output Discipline

The final answer must distinguish:

- External agent claims.
- Codex-verified facts.
- Unresolved conflicts.
- Tests or checks actually run.

Do not present external output as verified unless Codex independently verified it.
```

- [ ] **Step 4: Create implementation and review preset skills**

Create `skills/multi-agent-implementation/SKILL.md`:

```md
---
name: multi-agent-implementation
description: Use with multi-agent-orchestration for feature work, bug fixes, refactors, or implementation planning that benefits from external Claude, Copilot, or Antigravity input.
---

# Multi-Agent Implementation Preset

Load multi-agent-orchestration first. This skill only supplies the implementation brief structure and verification focus.

## Implementation Brief

Create an implementation brief with:

- Goal.
- Relevant files or search targets.
- Constraints from the user and repository instructions.
- Required behavior.
- Non-goals.
- Test expectations.
- Whether the external agent may propose a patch or must stay read-only.

Prefer patch proposals over direct writes. Direct writes require a git worktree or temporary copy.

## Result Requirements

Ask each external agent to return:

- Proposed approach.
- Files it would change.
- Patch or exact change summary.
- Tests it expects to pass.
- Risks and assumptions.

Codex must review the proposal before applying or adapting any change.
```

Create `skills/multi-agent-review/SKILL.md`:

```md
---
name: multi-agent-review
description: Use with multi-agent-orchestration for code review, regression analysis, test gap review, release risk review, or independent validation.
---

# Multi-Agent Review Preset

Load multi-agent-orchestration first. This skill only supplies the review brief structure and severity focus.

## Review Brief

Create a review brief with:

- Scope under review.
- Base branch or diff source when known.
- Files or modules to inspect.
- Review priorities: correctness, security, data loss, regressions, tests, maintainability.
- Output format with severity, file reference, evidence, and suggested fix.

## Result Requirements

Ask each external agent to return:

- Findings ordered by severity.
- File and line references when available.
- Why each issue matters.
- Suggested fix.
- Tests that would catch the issue.

Codex must verify each finding before presenting it as actionable.
```

- [ ] **Step 5: Run the skill tests**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "skill"
```

Expected: PASS for orchestration and preset assertions.

- [ ] **Step 6: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add skills mcp-server/test/skills.test.ts
git commit -m "feat: add multi-agent workflow skills"
```

### Task 3: Shared Result Schema

**Files:**
- Create: `mcp-server/src/common/result-schema.ts`
- Create: `mcp-server/test/result-schema.test.ts`

- [ ] **Step 1: Write the failing schema test**

Create `mcp-server/test/result-schema.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { AGENT_STATUSES, makeAgentResult, pluginIdentity } from "../src/common/result-schema.js";

test("plugin identity is stable", () => {
  assert.deepEqual(pluginIdentity, {
    name: "Integrated Agent Workflow",
    packageName: "integrated-agent-workflow",
    version: "0.1.0"
  });
});

test("agent statuses include expected failure modes", () => {
  assert.deepEqual(AGENT_STATUSES, [
    "ok",
    "unavailable",
    "unauthenticated",
    "timeout",
    "execution_failed",
    "invalid_output",
    "unsafe_request"
  ]);
});

test("makeAgentResult fills common metadata", () => {
  const result = makeAgentResult({
    agentId: "claude",
    displayName: "Claude Code",
    status: "ok",
    durationMs: 25,
    resultText: "Reviewed the code."
  });

  assert.equal(result.plugin.version, "0.1.0");
  assert.equal(result.agentId, "claude");
  assert.equal(result.status, "ok");
  assert.equal(result.resultText, "Reviewed the code.");
  assert.equal(typeof result.createdAt, "string");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "schema"
```

Expected: failure because `result-schema.ts` does not exist.

- [ ] **Step 3: Implement the shared result schema**

Create `mcp-server/src/common/result-schema.ts`:

```ts
export const pluginIdentity = {
  name: "Integrated Agent Workflow",
  packageName: "integrated-agent-workflow",
  version: "0.1.0"
} as const;

export const AGENT_STATUSES = [
  "ok",
  "unavailable",
  "unauthenticated",
  "timeout",
  "execution_failed",
  "invalid_output",
  "unsafe_request"
] as const;

export type AgentStatus = (typeof AGENT_STATUSES)[number];
export type AgentId = "claude" | "copilot" | "antigravity";
export type AgentPurpose = "implementation" | "review" | "general";
export type WritePolicy = "read_only" | "patch_proposal" | "isolated_write";

export interface AgentResult {
  plugin: typeof pluginIdentity;
  agentId: AgentId;
  displayName: string;
  status: AgentStatus;
  createdAt: string;
  durationMs: number;
  exitCode?: number | null;
  stdout?: string;
  stderrSummary?: string;
  resultText: string;
  logPath?: string;
  errorMessage?: string;
}

export interface AgentResultInput {
  agentId: AgentId;
  displayName: string;
  status: AgentStatus;
  durationMs: number;
  exitCode?: number | null;
  stdout?: string;
  stderrSummary?: string;
  resultText?: string;
  logPath?: string;
  errorMessage?: string;
}

export function makeAgentResult(input: AgentResultInput): AgentResult {
  return {
    plugin: pluginIdentity,
    agentId: input.agentId,
    displayName: input.displayName,
    status: input.status,
    createdAt: new Date().toISOString(),
    durationMs: input.durationMs,
    exitCode: input.exitCode,
    stdout: input.stdout,
    stderrSummary: input.stderrSummary,
    resultText: input.resultText ?? "",
    logPath: input.logPath,
    errorMessage: input.errorMessage
  };
}
```

- [ ] **Step 4: Run schema tests**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "schema"
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add mcp-server/src/common/result-schema.ts mcp-server/test/result-schema.test.ts
git commit -m "feat: add agent result schema"
```

### Task 4: Process Runner And Redaction

**Files:**
- Create: `mcp-server/src/common/process-runner.ts`
- Create: `mcp-server/src/common/redaction.ts`
- Create: `mcp-server/test/process-runner.test.ts`
- Create: `mcp-server/test/redaction.test.ts`

- [ ] **Step 1: Write failing redaction and runner tests**

Create `mcp-server/test/redaction.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { redactSecrets } from "../src/common/redaction.js";

test("redacts common secret shapes", () => {
  const input = "OPENAI_API_KEY=sk-test SECRET_TOKEN=abc123 password: hunter2";
  const output = redactSecrets(input);
  assert.equal(output.includes("sk-test"), false);
  assert.equal(output.includes("abc123"), false);
  assert.equal(output.includes("hunter2"), false);
  assert.match(output, /\[REDACTED\]/);
});
```

Create `mcp-server/test/process-runner.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { runProcess } from "../src/common/process-runner.js";

test("captures stdout and exit code", async () => {
  const result = await runProcess(process.execPath, ["-e", "console.log('hello')"], {
    cwd: process.cwd(),
    timeoutMs: 5_000
  });

  assert.equal(result.status, "ok");
  assert.equal(result.exitCode, 0);
  assert.match(result.stdout, /hello/);
});

test("marks timeout", async () => {
  const result = await runProcess(process.execPath, ["-e", "setTimeout(() => {}, 10000)"], {
    cwd: process.cwd(),
    timeoutMs: 50
  });

  assert.equal(result.status, "timeout");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "redacts|captures|timeout"
```

Expected: failures because common modules do not exist.

- [ ] **Step 3: Implement redaction**

Create `mcp-server/src/common/redaction.ts`:

```ts
const SECRET_PATTERNS: RegExp[] = [
  /\b(sk-[A-Za-z0-9_-]{4,})\b/g,
  /\b([A-Za-z0-9_]*TOKEN[A-Za-z0-9_]*\s*=\s*)([^\s]+)/gi,
  /\b([A-Za-z0-9_]*KEY[A-Za-z0-9_]*\s*=\s*)([^\s]+)/gi,
  /\b(password\s*[:=]\s*)([^\s]+)/gi
];

export function redactSecrets(value: string): string {
  let output = value;
  output = output.replace(SECRET_PATTERNS[0], "[REDACTED]");
  for (const pattern of SECRET_PATTERNS.slice(1)) {
    output = output.replace(pattern, "$1[REDACTED]");
  }
  return output;
}
```

- [ ] **Step 4: Implement process runner**

Create `mcp-server/src/common/process-runner.ts`:

```ts
import { spawn } from "node:child_process";
import { redactSecrets } from "./redaction.js";

export interface ProcessRunOptions {
  cwd: string;
  timeoutMs: number;
  input?: string;
}

export interface ProcessRunResult {
  status: "ok" | "timeout" | "execution_failed";
  exitCode: number | null;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export function runProcess(command: string, args: string[], options: ProcessRunOptions): Promise<ProcessRunResult> {
  const startedAt = Date.now();

  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill("SIGTERM");
      resolve({
        status: "timeout",
        exitCode: null,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(stderr),
        durationMs: Date.now() - startedAt
      });
    }, options.timeoutMs);

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });

    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        status: "execution_failed",
        exitCode: null,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(`${stderr}\n${error.message}`),
        durationMs: Date.now() - startedAt
      });
    });

    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        status: code === 0 ? "ok" : "execution_failed",
        exitCode: code,
        stdout: redactSecrets(stdout),
        stderr: redactSecrets(stderr),
        durationMs: Date.now() - startedAt
      });
    });

    if (options.input) {
      child.stdin.write(options.input);
    }
    child.stdin.end();
  });
}
```

- [ ] **Step 5: Run redaction and runner tests**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "redacts|captures|timeout"
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add mcp-server/src/common/process-runner.ts mcp-server/src/common/redaction.ts mcp-server/test/process-runner.test.ts mcp-server/test/redaction.test.ts
git commit -m "feat: add safe process runner"
```

### Task 5: CLI Adapter Contract

**Files:**
- Create: `mcp-server/src/adapters/types.ts`
- Create: `mcp-server/src/adapters/claude.ts`
- Create: `mcp-server/src/adapters/copilot.ts`
- Create: `mcp-server/src/adapters/antigravity.ts`
- Create: `mcp-server/src/adapters/index.ts`
- Create: `mcp-server/test/adapters.test.ts`

- [ ] **Step 1: Write failing adapter tests**

Create `mcp-server/test/adapters.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { adapters } from "../src/adapters/index.js";

test("registers all v1 adapters", () => {
  assert.deepEqual(Object.keys(adapters).sort(), ["antigravity", "claude", "copilot"]);
  assert.equal(adapters.claude.displayName, "Claude Code");
  assert.equal(adapters.copilot.displayName, "GitHub Copilot CLI");
  assert.equal(adapters.antigravity.displayName, "Google Antigravity CLI");
});

test("adapters build read-only commands", () => {
  const claude = adapters.claude.buildCommand("Review this.", { timeoutMs: 1000 });
  const copilot = adapters.copilot.buildCommand("Review this.", { timeoutMs: 1000 });
  const antigravity = adapters.antigravity.buildCommand("Review this.", { timeoutMs: 1000 });

  assert.equal(claude.command, "claude");
  assert.deepEqual(claude.args.slice(0, 1), ["-p"]);
  assert.equal(copilot.command, "copilot");
  assert.ok(copilot.args.includes("--prompt") || copilot.args.includes("-p"));
  assert.equal(antigravity.command, "agy");
  assert.ok(antigravity.args.includes("--prompt") || antigravity.args.includes("-p"));
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "adapter"
```

Expected: failure because adapters do not exist.

- [ ] **Step 3: Create adapter types**

Create `mcp-server/src/adapters/types.ts`:

```ts
import type { AgentId, AgentResult } from "../common/result-schema.js";

export interface BuiltCommand {
  command: string;
  args: string[];
  input?: string;
}

export interface BuildCommandOptions {
  timeoutMs: number;
}

export interface CliAdapter {
  id: AgentId;
  displayName: string;
  binaryName: string;
  versionArgs: string[];
  authHint: string;
  buildCommand(prompt: string, options: BuildCommandOptions): BuiltCommand;
}

export interface AgentExecutionRequest {
  cwd: string;
  prompt: string;
  timeoutMs: number;
}

export type AgentExecutionResponse = AgentResult;
```

- [ ] **Step 4: Create the three adapters and registry**

Create `mcp-server/src/adapters/claude.ts`:

```ts
import type { CliAdapter } from "./types.js";

export const claudeAdapter: CliAdapter = {
  id: "claude",
  displayName: "Claude Code",
  binaryName: "claude",
  versionArgs: ["--version"],
  authHint: "Run the Claude CLI login command, then rerun doctor.",
  buildCommand(prompt) {
    return {
      command: "claude",
      args: ["-p", prompt]
    };
  }
};
```

Create `mcp-server/src/adapters/copilot.ts`:

```ts
import type { CliAdapter } from "./types.js";

export const copilotAdapter: CliAdapter = {
  id: "copilot",
  displayName: "GitHub Copilot CLI",
  binaryName: "copilot",
  versionArgs: ["--version"],
  authHint: "Run the Copilot CLI auth or login command, then rerun doctor.",
  buildCommand(prompt) {
    return {
      command: "copilot",
      args: ["--prompt", prompt]
    };
  }
};
```

Create `mcp-server/src/adapters/antigravity.ts`:

```ts
import type { CliAdapter } from "./types.js";

export const antigravityAdapter: CliAdapter = {
  id: "antigravity",
  displayName: "Google Antigravity CLI",
  binaryName: "agy",
  versionArgs: ["--version"],
  authHint: "Run the Antigravity CLI auth or login command, then rerun doctor.",
  buildCommand(prompt) {
    return {
      command: "agy",
      args: ["--prompt", prompt]
    };
  }
};
```

Create `mcp-server/src/adapters/index.ts`:

```ts
import { antigravityAdapter } from "./antigravity.js";
import { claudeAdapter } from "./claude.js";
import { copilotAdapter } from "./copilot.js";

export const adapters = {
  claude: claudeAdapter,
  copilot: copilotAdapter,
  antigravity: antigravityAdapter
} as const;
```

- [ ] **Step 5: Run adapter tests**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "adapter"
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add mcp-server/src/adapters mcp-server/test/adapters.test.ts
git commit -m "feat: add CLI adapter contract"
```

### Task 6: Doctor Tool And Cache

**Files:**
- Create: `mcp-server/src/tools/doctor.ts`
- Create: `mcp-server/test/doctor.test.ts`

- [ ] **Step 1: Write the failing doctor test**

Create `mcp-server/test/doctor.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { createDoctorReport } from "../src/tools/doctor.js";

test("doctor reports all agents without secrets", async () => {
  const report = await createDoctorReport({
    cwd: process.cwd(),
    runVersionCheck: false,
    now: new Date("2026-06-29T00:00:00.000Z")
  });

  assert.equal(report.plugin.version, "0.1.0");
  assert.deepEqual(report.agents.map((agent) => agent.id).sort(), ["antigravity", "claude", "copilot"]);
  assert.equal(JSON.stringify(report).includes("token"), false);
  assert.equal(JSON.stringify(report).includes("secret"), false);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "doctor"
```

Expected: failure because doctor tool does not exist.

- [ ] **Step 3: Implement doctor report**

Create `mcp-server/src/tools/doctor.ts`:

```ts
import { existsSync } from "node:fs";
import { join } from "node:path";
import { adapters } from "../adapters/index.js";
import { pluginIdentity } from "../common/result-schema.js";
import { runProcess } from "../common/process-runner.js";

export interface DoctorOptions {
  cwd: string;
  runVersionCheck: boolean;
  now?: Date;
}

export interface DoctorAgentStatus {
  id: string;
  displayName: string;
  binaryName: string;
  status: "available" | "unavailable";
  version?: string;
  authHint: string;
}

export interface DoctorReport {
  plugin: typeof pluginIdentity;
  checkedAt: string;
  cwd: string;
  cachePath: string;
  agents: DoctorAgentStatus[];
}

export async function createDoctorReport(options: DoctorOptions): Promise<DoctorReport> {
  const agents: DoctorAgentStatus[] = [];

  for (const adapter of Object.values(adapters)) {
    let version: string | undefined;
    let status: "available" | "unavailable" = "unavailable";

    if (options.runVersionCheck) {
      const result = await runProcess(adapter.binaryName, adapter.versionArgs, {
        cwd: options.cwd,
        timeoutMs: 5_000
      });
      status = result.status === "ok" ? "available" : "unavailable";
      version = result.stdout.trim() || undefined;
    }

    agents.push({
      id: adapter.id,
      displayName: adapter.displayName,
      binaryName: adapter.binaryName,
      status,
      version,
      authHint: adapter.authHint
    });
  }

  return {
    plugin: pluginIdentity,
    checkedAt: (options.now ?? new Date()).toISOString(),
    cwd: options.cwd,
    cachePath: join(options.cwd, ".codex", "multi-agent", "cache", "doctor.json"),
    agents
  };
}

export function hasDoctorCache(cwd: string): boolean {
  return existsSync(join(cwd, ".codex", "multi-agent", "cache", "doctor.json"));
}
```

- [ ] **Step 4: Run doctor tests**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "doctor"
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add mcp-server/src/tools/doctor.ts mcp-server/test/doctor.test.ts
git commit -m "feat: add multi-agent doctor report"
```

### Task 7: Agent Execution Tools

**Files:**
- Create: `mcp-server/src/tools/run-agent.ts`
- Create: `mcp-server/src/tools/run-panel.ts`
- Create: `mcp-server/src/tools/summarize-results.ts`
- Create: `mcp-server/test/run-agent.test.ts`
- Create: `mcp-server/test/run-panel.test.ts`

- [ ] **Step 1: Write failing execution tool tests**

Create `mcp-server/test/run-agent.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { buildAgentPrompt, normalizeExecutionResult } from "../src/tools/run-agent.js";

test("buildAgentPrompt includes acceptance criteria and safety policy", () => {
  const prompt = buildAgentPrompt({
    task: "Review the plugin manifest.",
    purpose: "review",
    acceptanceCriteria: ["Find correctness issues.", "Do not modify files."],
    writePolicy: "read_only"
  });

  assert.match(prompt, /Review the plugin manifest/);
  assert.match(prompt, /Find correctness issues/);
  assert.match(prompt, /Do not modify files/);
  assert.match(prompt, /write policy: read_only/);
});

test("normalizeExecutionResult maps non-zero exit to execution_failed", () => {
  const result = normalizeExecutionResult({
    agentId: "claude",
    displayName: "Claude Code",
    processResult: {
      status: "execution_failed",
      exitCode: 1,
      stdout: "",
      stderr: "not logged in",
      durationMs: 10
    }
  });

  assert.equal(result.status, "execution_failed");
  assert.equal(result.stderrSummary, "not logged in");
});
```

Create `mcp-server/test/run-panel.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { summarizePanelStatus } from "../src/tools/run-panel.js";
import { makeAgentResult } from "../src/common/result-schema.js";

test("panel status is partial when at least one result is ok and one failed", () => {
  const status = summarizePanelStatus([
    makeAgentResult({ agentId: "claude", displayName: "Claude Code", status: "ok", durationMs: 1 }),
    makeAgentResult({ agentId: "copilot", displayName: "GitHub Copilot CLI", status: "timeout", durationMs: 1 })
  ]);

  assert.equal(status, "partial_success");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "AgentPrompt|panel status"
```

Expected: failure because execution tools do not exist.

- [ ] **Step 3: Implement run-agent helpers**

Create `mcp-server/src/tools/run-agent.ts`:

```ts
import type { AgentId, AgentPurpose, WritePolicy } from "../common/result-schema.js";
import { makeAgentResult } from "../common/result-schema.js";
import type { ProcessRunResult } from "../common/process-runner.js";

export interface BuildAgentPromptInput {
  task: string;
  purpose: AgentPurpose;
  acceptanceCriteria: string[];
  writePolicy: WritePolicy;
}

export function buildAgentPrompt(input: BuildAgentPromptInput): string {
  return [
    `Purpose: ${input.purpose}`,
    `Task: ${input.task}`,
    `Required write policy: ${input.writePolicy}`,
    "",
    "Acceptance criteria:",
    ...input.acceptanceCriteria.map((item) => `- ${item}`),
    "",
    "Return concise findings, proposed changes, risks, and tests. Do not claim you ran checks unless you actually ran them."
  ].join("\n");
}

export function normalizeExecutionResult(input: {
  agentId: AgentId;
  displayName: string;
  processResult: ProcessRunResult;
}) {
  return makeAgentResult({
    agentId: input.agentId,
    displayName: input.displayName,
    status: input.processResult.status === "ok" ? "ok" : input.processResult.status,
    durationMs: input.processResult.durationMs,
    exitCode: input.processResult.exitCode,
    stdout: input.processResult.stdout,
    stderrSummary: input.processResult.stderr.trim().slice(0, 1000),
    resultText: input.processResult.stdout.trim()
  });
}
```

- [ ] **Step 4: Implement run-panel and summarize helpers**

Create `mcp-server/src/tools/run-panel.ts`:

```ts
import type { AgentResult } from "../common/result-schema.js";

export type PanelStatus = "success" | "partial_success" | "failed";

export function summarizePanelStatus(results: AgentResult[]): PanelStatus {
  const okCount = results.filter((result) => result.status === "ok").length;
  if (okCount === results.length && results.length > 0) return "success";
  if (okCount > 0) return "partial_success";
  return "failed";
}
```

Create `mcp-server/src/tools/summarize-results.ts`:

```ts
import type { AgentResult } from "../common/result-schema.js";

export interface ResultSummary {
  okAgents: string[];
  failedAgents: Array<{ agent: string; status: string; message?: string }>;
  combinedText: string;
}

export function summarizeResults(results: AgentResult[]): ResultSummary {
  return {
    okAgents: results.filter((result) => result.status === "ok").map((result) => result.displayName),
    failedAgents: results
      .filter((result) => result.status !== "ok")
      .map((result) => ({ agent: result.displayName, status: result.status, message: result.errorMessage })),
    combinedText: results
      .filter((result) => result.resultText.trim().length > 0)
      .map((result) => `## ${result.displayName}\n\n${result.resultText}`)
      .join("\n\n")
  };
}
```

- [ ] **Step 5: Run execution tool tests**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "AgentPrompt|panel status"
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add mcp-server/src/tools mcp-server/test/run-agent.test.ts mcp-server/test/run-panel.test.ts
git commit -m "feat: add agent execution helpers"
```

### Task 8: MCP Server Registration

**Files:**
- Create: `mcp-server/src/server.ts`
- Create: `mcp-server/test/server-smoke.test.ts`

- [ ] **Step 1: Write failing server smoke test**

Create `mcp-server/test/server-smoke.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { listToolNames } from "../src/server.js";

test("server registers v1 tools", () => {
  assert.deepEqual(listToolNames().sort(), ["doctor", "run_agent", "run_panel", "summarize_results"]);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "server registers"
```

Expected: failure because server does not exist.

- [ ] **Step 3: Implement server module with tool names**

Create `mcp-server/src/server.ts`:

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { adapters } from "./adapters/index.js";
import { runProcess } from "./common/process-runner.js";
import { createDoctorReport } from "./tools/doctor.js";
import { buildAgentPrompt, normalizeExecutionResult } from "./tools/run-agent.js";
import { summarizePanelStatus } from "./tools/run-panel.js";
import { summarizeResults } from "./tools/summarize-results.js";

export function listToolNames(): string[] {
  return ["doctor", "run_agent", "run_panel", "summarize_results"];
}

export function createServer(): McpServer {
  const server = new McpServer({
    name: "integrated-agent-workflow",
    version: "0.1.0"
  });

  server.tool("doctor", { cwd: z.string().default(process.cwd()) }, async ({ cwd }) => {
    const report = await createDoctorReport({ cwd, runVersionCheck: true });
    return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }] };
  });

  server.tool(
    "run_agent",
    {
      agentId: z.enum(["claude", "copilot", "antigravity"]),
      cwd: z.string().default(process.cwd()),
      task: z.string(),
      purpose: z.enum(["implementation", "review", "general"]).default("general"),
      acceptanceCriteria: z.array(z.string()).default([]),
      writePolicy: z.enum(["read_only", "patch_proposal", "isolated_write"]).default("read_only"),
      timeoutMs: z.number().int().positive().default(120000)
    },
    async (input) => {
      const adapter = adapters[input.agentId];
      const prompt = buildAgentPrompt(input);
      const command = adapter.buildCommand(prompt, { timeoutMs: input.timeoutMs });
      const processResult = await runProcess(command.command, command.args, {
        cwd: input.cwd,
        timeoutMs: input.timeoutMs,
        input: command.input
      });
      const result = normalizeExecutionResult({
        agentId: adapter.id,
        displayName: adapter.displayName,
        processResult
      });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  );

  server.tool(
    "run_panel",
    {
      agentIds: z.array(z.enum(["claude", "copilot", "antigravity"])).default(["claude", "copilot", "antigravity"]),
      cwd: z.string().default(process.cwd()),
      task: z.string(),
      purpose: z.enum(["implementation", "review", "general"]).default("general"),
      acceptanceCriteria: z.array(z.string()).default([]),
      writePolicy: z.enum(["read_only", "patch_proposal", "isolated_write"]).default("read_only"),
      timeoutMs: z.number().int().positive().default(120000)
    },
    async (input) => {
      const results = [];
      for (const agentId of input.agentIds) {
        const adapter = adapters[agentId];
        const prompt = buildAgentPrompt(input);
        const command = adapter.buildCommand(prompt, { timeoutMs: input.timeoutMs });
        const processResult = await runProcess(command.command, command.args, {
          cwd: input.cwd,
          timeoutMs: input.timeoutMs,
          input: command.input
        });
        results.push(normalizeExecutionResult({ agentId: adapter.id, displayName: adapter.displayName, processResult }));
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

if (import.meta.url === `file://${process.argv[1]}`) {
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}
```

- [ ] **Step 4: Run server smoke test and build**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "server registers"
npm run build
```

Expected: test PASS and TypeScript build succeeds.

- [ ] **Step 5: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add mcp-server/src/server.ts mcp-server/test/server-smoke.test.ts
git commit -m "feat: register integrated agent MCP tools"
```

### Task 9: Documentation

**Files:**
- Create: `docs/authentication.md`
- Create: `docs/doctor.md`
- Create: `docs/security.md`
- Create: `docs/usage.md`
- Create: `mcp-server/test/docs.test.ts`

- [ ] **Step 1: Write failing docs test**

Create `mcp-server/test/docs.test.ts`:

```ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

for (const file of ["authentication.md", "doctor.md", "security.md", "usage.md"]) {
  test(`${file} includes plugin identity`, () => {
    const body = readFileSync(resolve(repoRoot, "docs", file), "utf8");
    assert.match(body, /Integrated Agent Workflow v0\.1\.0/);
  });
}

test("authentication docs explain one-time login model", () => {
  const body = readFileSync(resolve(repoRoot, "docs/authentication.md"), "utf8");
  assert.match(body, /not authenticate on every run/);
  assert.match(body, /does not store tokens/);
});
```

- [ ] **Step 2: Run docs test to verify it fails**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "docs|authentication"
```

Expected: failure because docs do not exist.

- [ ] **Step 3: Create authentication docs**

Create `docs/authentication.md`:

```md
# Integrated Agent Workflow v0.1.0 Authentication

Integrated Agent Workflow does not authenticate on every run. Each external CLI keeps its own login session, and this plugin uses the CLI state already present on the machine.

The plugin does not store tokens, passwords, OAuth refresh tokens, session cookies, or API keys.

## Setup

1. Install Claude Code CLI, GitHub Copilot CLI, and Google Antigravity CLI as needed.
2. Run each vendor's login command in your own terminal.
3. Run the plugin doctor workflow from Codex.
4. Re-run login only when doctor or an agent run reports that a session expired.

## Expected Commands

The implementation checks installed CLI help before relying on exact flags.

- Claude Code: run the Claude CLI login command shown by `claude --help`.
- GitHub Copilot CLI: run the Copilot auth or login command shown by `copilot --help`.
- Antigravity CLI: run the Antigravity auth or login command shown by `agy --help`.
```

- [ ] **Step 4: Create doctor, security, and usage docs**

Create `docs/doctor.md`:

```md
# Integrated Agent Workflow v0.1.0 Doctor

Doctor checks whether local external agent CLIs are ready.

It reports:

- Plugin name and version.
- Claude, Copilot, and Antigravity binary availability.
- Version output when available.
- Login guidance when an agent appears unavailable or unauthenticated.
- Non-secret cache path.

Doctor output is advisory. A later run can still fail if a CLI session expires after doctor runs.
```

Create `docs/security.md`:

```md
# Integrated Agent Workflow v0.1.0 Security

External agent output is advisory. Codex remains responsible for final verification.

The plugin must not include credential files, private keys, `.env` contents, access tokens, or session data in prompts.

Local run artifacts are written under `.codex/multi-agent/runs/` and cache artifacts under `.codex/multi-agent/cache/`. These paths are gitignored because prompts and results may contain private project context.

Write-capable external execution requires a git worktree or temporary copy. Direct writes to the active workspace are not the default behavior.
```

Create `docs/usage.md`:

```md
# Integrated Agent Workflow v0.1.0 Usage

Use this plugin when a Codex task is complex, risky, ambiguous, creative, or needs independent review.

Example implementation request:

```text
Use multi-agent implementation for this feature. Ask Claude, Copilot, and Antigravity for independent patch proposals, then verify and apply the best parts.
```

Example review request:

```text
Use multi-agent review on this branch. Prioritize correctness, regressions, missing tests, and security risks.
```

Codex may also select the orchestration skill automatically when the task description indicates that external validation would help.
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test -- --test-name-pattern "docs|authentication"
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add docs/authentication.md docs/doctor.md docs/security.md docs/usage.md mcp-server/test/docs.test.ts
git commit -m "docs: add integrated agent workflow guides"
```

### Task 10: Full Verification And Smoke Command

**Files:**
- Modify: `mcp-server/package.json`
- Create: `mcp-server/test/full-suite.test.ts`

- [ ] **Step 1: Write final verification test**

Create `mcp-server/test/full-suite.test.ts`:

```ts
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");

test("repository contains all v0.1.0 deliverables", () => {
  const requiredPaths = [
    ".codex-plugin/plugin.json",
    "README.md",
    "skills/multi-agent-orchestration/SKILL.md",
    "skills/multi-agent-implementation/SKILL.md",
    "skills/multi-agent-review/SKILL.md",
    "mcp-server/src/server.ts",
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
});
```

- [ ] **Step 2: Run full tests and build**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test
npm run build
```

Expected: all tests PASS and TypeScript emits `mcp-server/dist/server.js`.

- [ ] **Step 3: Run local doctor smoke if build succeeds**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
node .\mcp-server\dist\server.js --help
```

Expected: if the MCP server does not support `--help`, it should start as a stdio server and wait for MCP input. Stop it after confirming the built file starts without a module resolution error. If this blocks in the terminal, use Ctrl+C and record that startup reached stdio mode.

- [ ] **Step 4: Check working tree**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git status --short
```

Expected: only intentional Task 10 files are modified or untracked before commit.

- [ ] **Step 5: Commit**

Run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git add mcp-server/package.json mcp-server/test/full-suite.test.ts
git commit -m "test: add full plugin verification"
```

## Final Verification

After Task 10, run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트\mcp-server'
npm test
npm run build
```

Expected:

- All unit tests pass.
- TypeScript build succeeds.
- `mcp-server/dist/server.js` exists.

Then run:

```powershell
cd 'C:\Users\User\Documents\통합 에이전트'
git status --short
git log --oneline -5
```

Expected:

- Working tree is clean.
- Recent commits show the plan's task commits.

## Implementation Notes

- Before implementing, use `superpowers:using-git-worktrees` if execution should happen outside the current checkout.
- Use `superpowers:test-driven-development` for each implementation task because every task starts with a failing test.
- Use `superpowers:verification-before-completion` before claiming the plugin is complete.
- If exact CLI flags differ from the assumptions in this plan, update the adapter tests and docs in the same task that verifies the installed CLI help or official vendor documentation.
- Do not store or print tokens, passwords, OAuth session values, or `.env` file contents.
