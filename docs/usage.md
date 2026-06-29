# Integrated Agent Workflow v0.1.0 Usage

Use this plugin when a Codex task explicitly calls for external agents, or when the task is high-risk and independent validation is clearly worth the cost.

Example implementation request:

```text
Use multi-agent implementation for this feature. Ask Claude, Copilot, and Antigravity for independent patch proposals, then verify and apply the best parts.
```

Example review request:

```text
Use multi-agent review on this branch. Prioritize correctness, regressions, missing tests, and security risks.
```

Codex may also select the orchestration skill automatically when the task description indicates that independent external validation would help.
