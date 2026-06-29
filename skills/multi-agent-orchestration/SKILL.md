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
