# Integrated Agent Workflow v0.1.0 Security

External agent output is advisory. Codex remains responsible for final verification.

The plugin must not include credential files, private keys, `.env` contents, access tokens, or session data in prompts.

Local run artifacts are written under `.codex/multi-agent/runs/` and cache artifacts under `.codex/multi-agent/cache/`. These paths are gitignored because prompts and results may contain private project context.

Write-capable external execution requires a git worktree or temporary copy. Direct writes to the active workspace are not the default behavior.
