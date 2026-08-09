# Integrated Agent Workflow v0.5.0 Security

External agent output is advisory. Codex remains responsible for final verification.

The plugin must not include credential files, private keys, `.env` contents, access tokens, or session data in prompts.

Local run artifacts are written under `.codex/multi-agent/runs/` and cache artifacts under `.codex/multi-agent/cache/`. These paths are gitignored because prompts and results may contain private project context.

Generated logs, result files, and run artifacts must be redacted where possible, treated as potentially sensitive, and not shared casually.

Write-capable external execution requires a git worktree or temporary copy. Direct writes to the active workspace are not the default behavior.

Direct OpenAI agent runs use `codex exec --ephemeral --ignore-user-config` with plugins and nested multi-agent delegation disabled. Read-only and patch-proposal runs use the Codex `read-only` sandbox; isolated-write runs use `workspace-write` only after the plugin verifies that the target is a linked worktree.

LM Studio connection settings come from the MCP server environment rather than model-generated tool input. The base URL is limited to HTTP or HTTPS and rejects embedded credentials, query strings, and fragments. The configured server can see prompts and any context the local agent sends, so treat it as a trusted inference endpoint. Keep a remote server behind a trusted network boundary or enable LM Studio token authentication.

Prompts are kept out of command-line arguments. Codex, LM Studio through Codex, Claude, and Copilot receive them over stdin. Antigravity receives a restrictive temporary brief file because its current `--print` flag requires an argument; the file is removed when the process exits. All providers use plan or read-only modes unless `isolated_write` has passed the worktree safety check.
