# Integrated Agent Workflow v0.5.0

Integrated Agent Workflow is a Codex plugin that lets Codex coordinate OpenAI Codex CLI, LM Studio, Claude Code, GitHub Copilot CLI, and Google Antigravity CLI through a local MCP server.

The `codex` agent runs GPT models directly through `codex exec`; it does not route them through GitHub Copilot. Pass an exact model as `models.codex`, or omit it to use the isolated Codex run's effective default. The adapter ignores user configuration while still reusing saved Codex authentication.

The `lmstudio` agent runs the Codex agent harness against a configured LM Studio Responses endpoint. It defaults to `http://127.0.0.1:1234`; select a loaded model with `models.lmstudio` or `LMSTUDIO_MODEL`, and use `list_lmstudio_models` to refresh the model IDs reported by that server.

For difficult Claude work, the orchestration skill selects the fixed model ID `claude-opus-5` unless the user asks for a lower-cost or lower-latency choice. Claude JSON results expose observed model IDs separately from the requested model.

Codex remains the orchestrator and verifier. External agent output is advisory until Codex checks the final result.

## Quick Start

1. Install and authenticate the agent CLIs you want to use. The OpenAI agent reuses the current `codex login` session; LM Studio requires its configured server and model to be running.
2. Build the MCP server with `npm --prefix mcp-server install` and `npm --prefix mcp-server run build`.
3. Install or enable this plugin in Codex.
4. Ask Codex to use multi-agent review or implementation when a task is complex, risky, or benefits from independent opinions.

## Version

Integrated Agent Workflow v0.5.0
