---
name: multi-agent-orchestration
description: Use when the user explicitly asks for Claude, Copilot, Antigravity, external CLI agents, validation diversity, multi-agent execution, or independent review, or when high-risk work clearly warrants independent validation.
---

# Multi-Agent Orchestration

Codex is the coordinator and Codex remains the final verifier. External agent output is advisory until Codex checks the evidence, final diff, and relevant tests.

## Entry Decision

Use this workflow when one or more are true:

- The user asks for independent validation, multiple agents, Claude, Copilot, Antigravity, or diverse proposals.
- The task is high-risk because it touches release, security, data loss, authentication, payments, or broad refactors, and independent validation is clearly worth the cost.

Complex, creative, ambiguous, or multi-file tasks are useful signals that multi-agent help may be valuable.
Those signals alone do not permit automatic external CLI execution.
Run external CLIs automatically only when the user explicitly asks for them or when the task is high-risk and independent validation is clearly worth the cost.

Skip external CLI execution when all are true:

- The task is a small direct edit, typo fix, or simple command.
- Independent review would add little evidence.
- No external CLI is available and the task can be completed directly.

Ask for confirmation before any long-running, write-capable, or broad external execution.

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
