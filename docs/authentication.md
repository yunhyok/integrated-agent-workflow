# Integrated Agent Workflow v0.5.0 Authentication

Integrated Agent Workflow does not authenticate on every run. Each external CLI keeps its own login session, and this plugin uses the CLI state already present on the machine.

The plugin does not store tokens, passwords, OAuth refresh tokens, session cookies, or API keys.

## Setup

1. Install OpenAI Codex CLI, Claude Code CLI, GitHub Copilot CLI, and Google Antigravity CLI as needed.
2. Run each vendor's login command in your own terminal.
3. Run the plugin doctor workflow from Codex.
4. Re-run login only when doctor or an agent run reports that a session expired.

LM Studio does not require OpenAI login. The plugin defaults to the local LM Studio endpoint and can use a remote trusted endpoint through `LMSTUDIO_BASE_URL`. If token authentication is enabled, provide it only through the `LMSTUDIO_API_TOKEN` environment variable; never write the token into prompts, model names, or endpoint URLs.

## Expected Commands

The implementation checks installed CLI help before relying on exact flags.

- Claude Code: run the Claude CLI login command shown by `claude --help`.
- OpenAI Codex CLI: run `codex login`; direct GPT-agent runs reuse that saved session.
- LM Studio: start the server, load the configured model, and confirm `GET /v1/models` succeeds.
- GitHub Copilot CLI: run the Copilot auth or login command shown by `copilot --help`.
- Antigravity CLI: run the Antigravity auth or login command shown by `agy --help`.
