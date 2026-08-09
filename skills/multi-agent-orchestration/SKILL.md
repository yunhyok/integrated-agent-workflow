---
name: multi-agent-orchestration
description: Use when the user explicitly asks for OpenAI Codex, GPT, LM Studio, Claude, Copilot, Antigravity, external agents, validation diversity, multi-agent execution, or independent review, or when high-risk work clearly warrants independent validation.
---

# Multi-Agent Orchestration

Codex is the coordinator and Codex remains the final verifier. External agent output is advisory until Codex checks the evidence, final diff, and relevant tests.

## Entry Decision

Use this workflow when one or more are true:

- The user asks for independent validation, multiple agents, OpenAI Codex, GPT, LM Studio, Claude, Copilot, Antigravity, or diverse proposals.
- The task is high-risk because it touches release, security, data loss, authentication, payments, or broad refactors, and independent validation is clearly worth the cost.

Complex, creative, ambiguous, or multi-file tasks are useful signals that multi-agent help may be valuable.
Those signals alone do not permit automatic external CLI execution.
Run external CLIs automatically only when the user explicitly asks for them or when the task is high-risk and independent validation is clearly worth the cost.

Skip external CLI execution when all are true:

- The task is a small direct edit, typo fix, or simple command.
- Independent review would add little evidence.
- No external CLI is available and the task can be completed directly.

Ask for confirmation before any long-running, write-capable, or broad external execution.
Treat a requested timeout above 600000 ms as long-running unless the user explicitly authorized that duration. Keep a single read-only agent run at or below 600000 ms by default.

## Workflow

1. Restate the task, constraints, and acceptance criteria.
2. Select the preset: implementation, review, or general.
3. Call `doctor` on the integrated agent runner MCP server.
4. Choose available agents from OpenAI Codex, LM Studio, Claude, Copilot, and Antigravity. Use agent ID `codex` for direct GPT-model execution through the OpenAI Codex CLI, `lmstudio` for the configured LM Studio Responses server, and `antigravity` for Google Antigravity CLI.
5. Pass model choices through the `models` map keyed by `codex`, `lmstudio`, `claude`, `copilot`, and `antigravity`. Preserve every exact model the user specifies. Before using LM Studio when server state may have changed, call `list_lmstudio_models`; do not add LM Studio to a default panel unless it was explicitly selected. Apply the Claude routing policy below only when the user did not choose a Claude model. The direct `codex` agent uses its isolated run default because the adapter intentionally ignores user configuration while preserving authentication.
6. Build one concise brief per agent with identical acceptance criteria.
7. Prefer read-only or patch-proposal mode unless isolated write execution is explicitly safe.
8. Call `run_panel` for independent execution or `run_agent` for one target.
9. Compare returned results for agreement, conflicts, missing evidence, and risky assumptions.
10. Verify the final answer through direct Codex inspection, tests, or command output.
11. Report which external agents contributed usable output and which failed, including requested model metadata when present.

## Claude Model Routing

- When Claude is selected for difficult multi-file implementation, long-horizon agentic work, architecture, hard debugging, release-risk review, or high-risk validation, set `models.claude` to the exact ID `claude-opus-5` unless the user prioritizes lower cost or latency.
- For routine or throughput-sensitive work, use `claude-sonnet-5` when an explicit Claude model is useful, or leave the provider default unchanged.
- Never use the `opus` alias when Opus 5 is required. Alias resolution can lag the newest fixed model ID.
- Do not silently substitute another Claude model after an explicit Opus 5 request fails. Report the access or execution failure and continue with other selected agents when useful.
- Opus 5 may delegate readily. In its brief, allow nested subagents only for independent, substantial work and set a small explicit cap; keep the primary Claude agent accountable for integration and verification.

## Output Discipline

The final answer must distinguish:

- External agent claims.
- Codex-verified facts.
- Unresolved conflicts.
- Tests or checks actually run.
- Requested model metadata from the tool result when present.
- `observedModels` and `modelMatch` when the Claude CLI returns JSON model-usage evidence. Treat `confirmed` as exact full-ID evidence, `mismatch` as a resolved model different from the requested string, and `unverified` as no transport-level proof. Auxiliary models may also appear in `observedModels`.
- LM Studio results remain `unverified` unless response-level transport evidence identifies the served model; the requested model or a Codex execution header alone is not confirmation.

Do not present external output as verified unless Codex independently verified it.
