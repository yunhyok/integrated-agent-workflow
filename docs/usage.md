# Integrated Agent Workflow v0.5.0 Usage

Use this plugin when a Codex task explicitly calls for external agents, or when the task is high-risk and independent validation is clearly worth the cost.

Complex, creative, ambiguous, or multi-file tasks are useful signals that multi-agent help may be valuable, but those signals alone do not permit automatic external CLI execution.

Example implementation request:

```text
Use multi-agent implementation for this feature. Ask OpenAI Codex, Claude, Copilot, and Antigravity for independent patch proposals, then verify and apply the best parts.
```

Example review request:

```text
Use multi-agent review on this branch. Prioritize correctness, regressions, missing tests, and security risks.
```

To run a GPT model directly as an agent, select `codex` and provide the model under `models.codex`:

```json
{
  "agentId": "codex",
  "models": {
    "codex": "gpt-5.4"
  },
  "writePolicy": "read_only"
}
```

This invokes OpenAI Codex CLI directly with `codex exec --model`; it does not use GitHub Copilot. Model availability still depends on the account and Codex CLI. If `models.codex` is omitted, the isolated Codex run chooses its effective default; the adapter intentionally ignores user configuration while preserving saved authentication.

To use a loaded LM Studio model, select `lmstudio`:

```json
{
  "agentId": "lmstudio",
  "models": {
    "lmstudio": "your-loaded-model-id"
  },
  "writePolicy": "read_only",
  "timeoutMs": 300000
}
```

The MCP host allows 660 seconds per tool call so the documented maximum 600-second agent run still has time to return a structured result and clean up its child process.

The public MCP configuration does not pin deployment-specific LM Studio values. The server defaults to `http://127.0.0.1:1234`; set `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL`, `LMSTUDIO_CONTEXT_WINDOW`, and optionally `LMSTUDIO_API_TOKEN` in the MCP host environment when different values are needed. A model passed as `models.lmstudio` takes precedence over `LMSTUDIO_MODEL`. Call `list_lmstudio_models` before selection when the server's loaded models may have changed. It reads both LM Studio model endpoints, filters out embeddings, and preserves loaded-instance IDs. LM Studio is selectable but is not added to the default `run_panel` set because local inference latency and availability vary.

When cost, latency, or capability matters, pass per-agent model selections instead of relying on each CLI default:

```json
{
  "models": {
    "codex": "gpt-5.4",
    "lmstudio": "your-loaded-model-id",
    "claude": "claude-opus-5",
    "antigravity": "Gemini 3.1 Pro (High)",
    "copilot": "gpt-5.3-codex"
  }
}
```

For difficult multi-file implementation, long-horizon work, hard debugging, and high-risk review, the orchestration skill selects the exact Claude ID `claude-opus-5` unless the user prioritizes lower cost or latency. Use `claude-sonnet-5` for routine or throughput-sensitive work. Do not use the `opus` alias when Opus 5 is required because an alias can still resolve to an earlier Opus release.

The requested model is forwarded to the provider CLI and included in result metadata as `requestedModel`. A selected model also appears in the display name, such as `Claude Code (claude-opus-5)` or `LM Studio Remote (your-loaded-model-id)`. Claude runs use JSON output so the runner can preserve transport evidence as `observedModels` and classify `modelMatch` as `confirmed`, `mismatch`, or `unverified`. Claude helper models can appear alongside the primary model. A result is confirmed only when the exact requested full ID appears in provider output that the runner parses. LM Studio-through-Codex results remain `unverified` because the Codex CLI execution header proves the selected configuration, not the model identity returned by the inference server.

When Opus 5 is used, keep nested delegation bounded: allow Claude subagents only for independent, substantial work, set a small explicit cap, and require the primary Claude agent to integrate and verify their output.

On Windows, the runner resolves native executables bundled by Codex, Claude, and Copilot plus the Antigravity install directory directly. This avoids PowerShell execution-policy failures. The LM Studio adapter reuses the resolved Codex executable and defines an isolated custom Responses provider on each run. Prompts use stdin except for Antigravity, where a short-lived restrictive temporary brief file keeps task text out of the process argument list.

Codex may select the orchestration skill automatically only when the user explicitly asks for external agents or when the task is high-risk and independent validation is clearly worth the cost.
