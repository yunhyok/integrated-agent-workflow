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
