# Integrated Agent Workflow v0.1.0 Design

## Purpose

Integrated Agent Workflow v0.1.0 is a Codex plugin that lets Codex coordinate
multiple external agent CLIs while remaining the final orchestrator and
verifier.

The plugin targets three external agents in v1:

- Claude Code CLI
- GitHub Copilot CLI
- Google Antigravity CLI

Codex decides when multi-agent execution is useful, divides the task, runs
available external CLIs through a local MCP server, compares the returned
results, and verifies the final outcome before reporting completion.

## Scope

v1 provides:

- A reusable Codex plugin package.
- A core orchestration skill.
- Two purpose preset skills: implementation and review.
- A local MCP server that exposes external CLI execution tools to Codex.
- CLI adapters for Claude, Copilot, and Antigravity.
- Doctor, execution, result-normalization, and summary workflows.
- Installation, authentication, doctor, security, and usage documentation.

v1 does not:

- Store service passwords, API keys, OAuth tokens, or session secrets.
- Automatically install Claude, Copilot, or Antigravity.
- Trust external agent output without Codex review.
- Let external agents freely modify the active workspace by default.
- Require the user to manually invoke the skill every time.

## Architecture

The plugin is named `integrated-agent-workflow` and starts at version `0.1.0`.
The name and version must be visible in:

- `.codex-plugin/plugin.json`
- `README.md`
- `doctor` output
- run log metadata

The plugin contains three skills:

- `multi-agent-orchestration`: the central workflow for task decomposition,
  agent selection, result comparison, and final Codex verification.
- `multi-agent-implementation`: a preset for feature work, bug fixes, and code
  changes.
- `multi-agent-review`: a preset for code review, risk assessment, and
  independent validation.

The plugin also contains a local MCP server. The skills decide what should
happen. The MCP server only executes local tools and returns structured
results.

This separation keeps workflow policy independent from CLI-specific behavior.
If a vendor changes its CLI flags later, the adapter can change without
rewriting the orchestration skill.

## Expected File Layout

```text
integrated-agent-workflow/
  .codex-plugin/
    plugin.json
  skills/
    multi-agent-orchestration/
      SKILL.md
    multi-agent-implementation/
      SKILL.md
    multi-agent-review/
      SKILL.md
  mcp-server/
    package.json
    src/
      server.ts
      tools/
        doctor.ts
        run-agent.ts
        run-panel.ts
        summarize-results.ts
      adapters/
        claude.ts
        copilot.ts
        antigravity.ts
      common/
        result-schema.ts
        process-runner.ts
        redaction.ts
        workspace-safety.ts
    templates/
      implementation-brief.md
      review-brief.md
      result-schema.md
  docs/
    authentication.md
    doctor.md
    security.md
    usage.md
  README.md
```

## Skill Selection

The user can explicitly ask for the plugin, but v1 should also support
automatic Codex skill selection through strong skill descriptions.

`multi-agent-orchestration` should describe itself as useful when a task is:

- Complex or ambiguous.
- High-risk.
- Spread across multiple modules or files.
- Creative and benefits from diversity.
- In need of independent review.
- Explicitly about Claude, Copilot, Antigravity, external agents, or
  multi-agent execution.

The skill should still make a lightweight entry decision before running
external CLIs. It should use multi-agent execution when the expected value is
clear, and skip it for small direct tasks such as typo fixes, simple command
execution, or narrowly scoped single-file edits.

Long-running, expensive, broad, or write-capable external execution should be
summarized for the user before execution.

## MCP Tools

The local MCP server exposes four v1 tools.

### `doctor`

Checks the local environment and returns structured status for:

- Plugin name and version.
- CLI binary path for `claude`, `copilot`, and `agy`.
- CLI version when available.
- Authentication status estimate.
- Dry-run prompt support when safe.
- Git repository status.
- Whether the current workspace is dirty.
- Whether isolated write execution is available.

The tool never reads or returns secret token values.

### `run_agent`

Runs one external agent against one brief.

Inputs include:

- Agent id: `claude`, `copilot`, or `antigravity`.
- Task brief.
- Purpose: `implementation`, `review`, or `general`.
- Working directory.
- Write policy.
- Timeout.
- Optional output schema preference.

Outputs include:

- Agent id and display name.
- Status.
- Exit code.
- Duration.
- Normalized stdout.
- Normalized stderr summary.
- Result text.
- Parsed structured result when available.
- Log path.

### `run_panel`

Runs the same task against multiple agents. It may run agents in parallel when
safe or sequentially when the target workflow requires strict ordering.

One failed agent must not fail the whole panel. The tool returns all available
results and a partial-success status when at least one agent returns usable
output.

### `summarize_results`

Normalizes and groups returned agent results for Codex. This tool is a helper,
not the final decision maker. Codex still performs the final judgment and
verification.

## CLI Adapters

Each adapter implements the same contract:

- Detect CLI binary.
- Detect version.
- Check likely authentication status.
- Build the command safely.
- Run the process with timeout.
- Capture stdout, stderr, exit code, and duration.
- Normalize known failure modes.
- Redact sensitive data before storing logs.

Initial command assumptions:

- Claude Code: use the `claude` CLI and non-interactive print mode where
  available.
- GitHub Copilot CLI: use the `copilot` CLI and prompt/non-interactive mode
  where available.
- Antigravity CLI: use the `agy` CLI and prompt/non-interactive mode where
  available.

The implementation must verify actual installed commands through `--help`,
version checks, and official documentation before finalizing adapter flags.

## Authentication

The plugin does not authenticate directly with any vendor service. The user
authenticates once through each vendor CLI, and the plugin reuses the CLI's
existing login state.

Normal setup flow:

```text
1. Install each desired CLI.
2. Run the vendor CLI login command.
3. Run the plugin doctor command.
4. Use Codex normally.
```

Expected user guidance:

```text
Claude Code: not authenticated
Run the Claude CLI login command, then rerun doctor.
```

```text
GitHub Copilot CLI: not authenticated
Run the Copilot CLI auth/login command, then rerun doctor.
```

```text
Antigravity CLI: not authenticated
Run the Antigravity CLI auth/login command, then rerun doctor.
```

The exact login commands must be confirmed during implementation from the
installed CLI help or official vendor documentation.

Authentication is not required on every plugin use. The plugin should cache
non-secret doctor status under `.codex/multi-agent/cache/doctor.json` with a
default TTL such as 24 hours. The cache may include CLI path, version, status,
and timestamp. It must not include tokens, session cookies, or secret values.

If a run fails as unauthenticated, the cache for that agent is invalidated and
the user is shown the appropriate login guidance.

## Data Flow

1. User gives Codex a task.
2. Codex loads the orchestration skill automatically or by explicit request.
3. The orchestration skill decides whether multi-agent execution is worth it.
4. The implementation or review preset shapes the task brief.
5. Codex calls `doctor` to determine usable external agents.
6. Codex calls `run_panel` or `run_agent`.
7. Each adapter calls its CLI and stores sanitized run logs.
8. The MCP server returns normalized results.
9. Codex compares common points, conflicts, missing evidence, and risks.
10. Codex performs final verification through normal repo inspection, tests, or
    review.
11. Codex reports the final result and clearly states which external agents
    contributed usable output.

## Safety

External agent output is advisory. Codex remains responsible for final
decisions.

Default policies:

- Review and analysis prompts may run against the current workspace.
- Implementation prompts should request plans, patches, or proposed changes by
  default.
- Direct file modification by external agents requires isolation in a git
  worktree or temporary copy.
- Generated patches must be reviewed by Codex before applying.
- The workflow is not complete until Codex verifies the final diff and relevant
  tests or checks.

The MCP server must redact likely secrets from prompts and logs. It should not
include `.env`, credential files, private keys, access tokens, or session data
in prompts.

Run artifacts are stored under:

```text
.codex/multi-agent/runs/<run-id>/
```

This directory must be ignored by git because prompts and model outputs may
contain sensitive project context.

## Failure Handling

Every external agent result uses one of these statuses:

- `ok`
- `unavailable`
- `unauthenticated`
- `timeout`
- `execution_failed`
- `invalid_output`
- `unsafe_request`

`run_panel` returns partial results when possible. Codex must report:

- Which agents ran.
- Which agents failed.
- Why they failed.
- Whether enough independent evidence remains to proceed.
- What fallback validation Codex performed.

## Testing

Adapter tests should not require the real vendor CLIs. They should cover:

- Binary detection.
- Version parsing.
- Authentication failure parsing.
- Timeout handling.
- Unavailable CLI handling.
- stdout/stderr/result normalization.

MCP server tests should cover:

- `doctor`
- `run_agent`
- `run_panel`
- `summarize_results`
- partial panel failure
- redaction behavior
- schema stability

Smoke tests are conditional. If the relevant CLI is installed and logged in,
the smoke test sends a short read-only prompt and confirms that the result is
captured and normalized. If not, the smoke test reports skipped agents rather
than failing the whole suite.

## Documentation

Required docs:

- `README.md`: quick start, plugin identity, supported agents, common commands.
- `docs/authentication.md`: how users authenticate each service and rerun
  doctor.
- `docs/doctor.md`: expected doctor output and troubleshooting.
- `docs/security.md`: secret handling, logs, write isolation, and limitations.
- `docs/usage.md`: examples for implementation and review workflows.

## Open Questions For Implementation

These are implementation-time checks, not design blockers:

- Confirm exact current non-interactive flags for Claude Code CLI.
- Confirm exact current non-interactive flags for GitHub Copilot CLI.
- Confirm exact current non-interactive flags for Antigravity `agy` CLI.
- Decide whether the MCP server is implemented in TypeScript or Python after
  checking existing Codex plugin examples and local runtime preference.
- Decide the exact public command or prompt users should run to invoke doctor
  once the plugin manifest and MCP tool names are finalized.

## Approval Summary

The approved v1 design is:

- Codex plugin package.
- Core orchestration skill plus implementation and review preset skills.
- Automatic skill selection when task complexity warrants it.
- Local MCP server for direct Claude, Copilot, and Antigravity CLI execution.
- User-managed one-time CLI authentication with cached non-secret status.
- Safe partial failure handling.
- Codex-controlled final verification.
