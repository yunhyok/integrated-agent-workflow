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
