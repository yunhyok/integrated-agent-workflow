import assert from "node:assert/strict";
import test from "node:test";
import {
  buildAgentPrompt,
  makeUnsafeWorkspaceResult,
  normalizeExecutionResult,
  parseClaudeJsonOutput
} from "../src/tools/run-agent.js";

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

test("buildAgentPrompt redacts secrets from task and acceptance criteria", () => {
  const prompt = buildAgentPrompt({
    task: "Review this token sk-test12345 and API_KEY=abc123.",
    purpose: "review",
    acceptanceCriteria: ["Do not leak password: hunter2."],
    writePolicy: "read_only"
  });

  assert.equal(prompt.includes("sk-test12345"), false);
  assert.equal(prompt.includes("API_KEY=abc123"), false);
  assert.equal(prompt.includes("password: hunter2"), false);
  assert.match(prompt, /\[REDACTED\]/);
});

test("normalizeExecutionResult maps auth-looking failures to unauthenticated", () => {
  const result = normalizeExecutionResult({
    agentId: "codex",
    displayName: "OpenAI Codex CLI (gpt-5.4)",
    requestedModel: "gpt-5.4",
    processResult: {
      status: "execution_failed",
      exitCode: 1,
      stdout: "",
      stderr: "not logged in",
      durationMs: 10
    }
  });

  assert.equal(result.status, "unauthenticated");
  assert.equal(result.displayName, "OpenAI Codex CLI (gpt-5.4)");
  assert.equal(result.requestedModel, "gpt-5.4");
  assert.equal(result.modelMatch, "unverified");
  assert.equal(result.stderrSummary, "not logged in");
});

test("parseClaudeJsonOutput extracts result text and all observed models", () => {
  const parsed = parseClaudeJsonOutput(
    JSON.stringify({
      type: "result",
      result: "Reviewed the code.",
      modelUsage: {
        "claude-haiku-4-5-20251001": { inputTokens: 1 },
        "claude-opus-5": { inputTokens: 2 }
      }
    })
  );

  assert.deepEqual(parsed, {
    resultText: "Reviewed the code.",
    observedModels: ["claude-haiku-4-5-20251001", "claude-opus-5"],
    isError: false
  });
});

test("normalizeExecutionResult confirms the exact Claude Opus 5 model from CLI JSON", () => {
  const result = normalizeExecutionResult({
    agentId: "claude",
    displayName: "Claude Code (claude-opus-5)",
    requestedModel: "claude-opus-5",
    processResult: {
      status: "ok",
      exitCode: 0,
      stdout: JSON.stringify({
        type: "result",
        result: "OPUS5_OK",
        modelUsage: {
          "claude-haiku-4-5-20251001": {},
          "claude-opus-5": {}
        }
      }),
      stderr: "",
      durationMs: 10
    }
  });

  assert.equal(result.status, "ok");
  assert.equal(result.resultText, "OPUS5_OK");
  assert.deepEqual(result.observedModels, ["claude-haiku-4-5-20251001", "claude-opus-5"]);
  assert.equal(result.modelMatch, "confirmed");
  assert.equal(result.modelObservationSource, "claude_cli_json_modelUsage");
});

test("normalizeExecutionResult reports alias resolution as a mismatch", () => {
  const result = normalizeExecutionResult({
    agentId: "claude",
    displayName: "Claude Code (opus)",
    requestedModel: "opus",
    processResult: {
      status: "ok",
      exitCode: 0,
      stdout: JSON.stringify({
        type: "result",
        result: "OK",
        modelUsage: { "claude-opus-4-8": {} }
      }),
      stderr: "",
      durationMs: 10
    }
  });

  assert.equal(result.modelMatch, "mismatch");
  assert.deepEqual(result.observedModels, ["claude-opus-4-8"]);
});

test("normalizeExecutionResult does not treat Claude error JSON with exit zero as success", () => {
  const result = normalizeExecutionResult({
    agentId: "claude",
    displayName: "Claude Code (claude-opus-5)",
    requestedModel: "claude-opus-5",
    processResult: {
      status: "ok",
      exitCode: 0,
      stdout: JSON.stringify({
        type: "result",
        subtype: "error_during_execution",
        is_error: true,
        api_error_status: 529,
        result: "Service temporarily unavailable.",
        modelUsage: { "claude-opus-5": {} }
      }),
      stderr: "",
      durationMs: 10
    }
  });

  assert.equal(result.status, "execution_failed");
  assert.equal(result.modelMatch, "confirmed");
  assert.match(result.errorMessage ?? "", /Service temporarily unavailable/);
});

test("normalizeExecutionResult marks invalid Claude JSON as invalid_output", () => {
  const result = normalizeExecutionResult({
    agentId: "claude",
    displayName: "Claude Code (claude-opus-5)",
    requestedModel: "claude-opus-5",
    processResult: {
      status: "ok",
      exitCode: 0,
      stdout: "not-json",
      stderr: "",
      durationMs: 10
    }
  });

  assert.equal(result.status, "invalid_output");
  assert.equal(result.modelMatch, "unverified");
  assert.match(result.errorMessage ?? "", /not valid result JSON/);
});

test("makeUnsafeWorkspaceResult returns unsafe_request without execution details", () => {
  const result = makeUnsafeWorkspaceResult({
    agentId: "codex",
    displayName: "OpenAI Codex CLI (gpt-5.4)",
    requestedModel: "gpt-5.4",
    reason: "isolated_write requires an isolated linked worktree"
  });

  assert.equal(result.status, "unsafe_request");
  assert.equal(result.displayName, "OpenAI Codex CLI (gpt-5.4)");
  assert.equal(result.requestedModel, "gpt-5.4");
  assert.equal(result.modelMatch, "unverified");
  assert.equal(result.durationMs, 0);
  assert.equal(result.errorMessage, "isolated_write requires an isolated linked worktree");
  assert.equal(result.stdout, undefined);
});
