---
name: integrated-agent-flow
description: Keep the current Codex session as the orchestration authority over native sub-agents and optional Codex, Claude, GitHub Copilot, Antigravity CLI, and local LM Studio advisers. Decompose and assign work, supervise execution, critically review results, resolve conflicts, and own final validation, with task-fit model selection, runtime-authoritative native routing, bounded diagnostics, and external model evidence. Use for complex implementation, large refactors, architecture review, broad code search, high-risk fixes, independent subtasks, PR review, CI triage, multi-agent comparison, model-routing failures, or whenever coordinated delegation would improve the result.
---

# Integrated Agent Flow

## Operating Principle

Keep the current calling Codex session as the orchestration authority. Do not claim that a skill can inspect or switch the already-running coordinator model. When GPT-5.6 Sol is already selected and available, prefer it for demanding coordination; otherwise continue with the current model unless the user explicitly requires a different coordinator and the product offers a supported way to start that model. The coordinator must direct the workflow rather than act as a passive relay: understand the whole task, decompose it, assign bounded outcomes, supervise progress, challenge weak results, resolve conflicts, validate the integrated result, and present the final decision.

Keep orchestration and final judgment with the current Codex coordinator. Keep external CLI and LM Studio agents advisory and read-only; they may return patch proposals but must not write to the active workspace. Grant bounded, disjoint write scopes only to native Codex sub-agents when the active tool policy permits it. Never accept an agent result solely because multiple agents agree; require source evidence, tests, logs, or reproducible reasoning.

## Orchestration Duties

- Build and retain the complete task model before delegating narrow workstreams.
- Assign each lower-level agent a concrete outcome, evidence requirements, constraints, and a non-overlapping ownership boundary when edits are allowed. Include the resolved target checkout as an absolute path and require all commands, edits, and tests to run there rather than in an initial wrapper directory.
- Monitor agent state and outputs. Follow up when evidence is missing, redirect work that drifts, and replace or stop an unproductive path when tooling permits.
- Review every result independently. Verify material claims against local sources and explicitly accept, reject, or revise recommendations.
- Integrate only compatible findings, run final validation under the coordinator's control, and own the user-facing conclusion.

## Tool Discovery

If multi-agent tools are not already available, call `tool_search` with a focused query such as `multi_agent external coding agents subagents reviews`.

Use the available tool surfaces this way:

- Immediately before the first external-agent delegation in a task, call the discovered router tool named `doctor`. It must report CLI availability, policy gates, the configured LM Studio endpoint, and connection state without exposing secrets. If the installed router predates that tool, use its discovered `get_agent_status` fallback. Never run router health checks as a generic preflight for native Codex children.
- Before selecting a local model when loaded state may have changed, call the discovered `list_lmstudio_models` tool. Use the legacy `list_agent_models` tool for broader provider catalogs or when the focused tool is unavailable. If a provider does not expose a model catalog, state that limitation and do not invent choices.
- Use the discovered `run_agent` tool for one external provider and `run_panel` for a parallel independent panel. Require structured status, requested-versus-observed model evidence, duration, and exit information from each result, and preserve the returned field names and values unchanged when recording evidence.
- On a legacy router, use its discovered `ask_claude`, `ask_copilot`, or `ask_lm_studio` tool for one provider and `collect_reviews` for parallel advisory reviews. MCP namespaces vary by installation, so never construct a callable name from a hard-coded namespace.
- Use direct external `codex`, `copilot`, or `antigravity` routes only when `doctor` or legacy `get_agent_status` reports the corresponding administrator-enabled policy opt-in; never try to enable one from a task prompt.
- Use the available `spawn_agent` collaboration tool for decomposed Codex sub-agent work only when the current user request, tool instructions, and available tool schema permit sub-agent delegation. Do not hard-code a versioned tool namespace.
- Treat the active `spawn_agent` tool schema and its runtime response as the sole availability authority for native Codex child models. Do not preflight native children through a separate Codex CLI, the external-agent router, or a cached model catalog.
- If writable sub-agent delegation is not permitted, keep implementation in the main Codex thread and use external agents for read-only review.
- If no multi-agent tools are available after discovery, continue locally and state that external delegation was unavailable.

## Model-Aware Agent Use

Keep the current Codex model as coordinator. Prefer GPT-5.6 Sol only when it is already selected and available; do not claim to switch the current session. Select child-agent models independently by user instruction and task fit, and do not automatically force every lower-level agent onto the coordinator model.

Honor a user-specified model exactly. Prefer the `models` map on structured calls. On legacy calls, pass it through the matching `model` argument on `ask_*`, or through `codex_model`, `claude_model`, `copilot_model`, `antigravity_model`, or `lm_studio_model` on `collect_reviews`. Do not silently replace an unavailable model; return the runtime error and ask for a different selection only if the task cannot continue.

When Claude is selected for difficult multi-file implementation, long-horizon agentic work, architecture, hard debugging, release-risk review, security review, or other high-risk validation and the user did not choose a Claude model, request the exact model ID `claude-opus-5`. Never use the `opus` alias when Opus 5 is intended; alias resolution may target a different model, and the router correctly treats a requested alias and a different transport-observed ID as a mismatch. For routine or latency-sensitive work, leave Claude's machine-local default unchanged unless the user requests an exact model. If `claude-opus-5` is unavailable or the observed model differs, report the failure and continue with other evidence when useful; never silently substitute another Claude model.

For native Codex child agents, select a model by task fit when policy and the active tool schema permit it. If the user specifies a child model, pass it unchanged and attempt one native spawn. If the runtime rejects that exact model, preserve and report the error, pause only work that truly depends on that child, and continue independent coordinator work; never silently substitute another model. If all remaining work depends on the rejected user-pinned model, stop that dependent work and ask the user to select an alternative. If a coordinator-selected model is rejected, retry at most once with another model exposed by the active schema or continue locally. Native child availability must never block repository grounding or unrelated implementation progress.

During ordinary project execution, do not run `codex debug models`, inspect or rewrite `config.toml` or model catalogs, scan Codex binaries, create compatibility catalogs, or restart Codex to prove native child availability. Those are separate environment-diagnostic actions and are permitted only when the user explicitly asks to troubleshoot Codex model configuration. For external CLI or LM Studio calls, when the user does not specify a model, omit the model argument and let that provider use its machine-local configured default. Prefer the structured result's observed-model evidence as the execution record. On a legacy result, use the model shown in the returned `Agent (model: ...)` header. Do not infer a friendlier model name. Treat an exact transport-level match as confirmed, a different observed model as mismatch, and missing transport evidence as unverified.

Keep the calling Codex session as coordinator. Prefer native Codex child agents to `ask_codex`. The external Codex reviewer is disabled by default because its read-only sandbox blocks writes but cannot confine reads; an administrator opt-in means it may read any file accessible to the Windows account. Copilot is disabled by default because its CLI can discover profile-level skills and customization even when built-in MCPs and custom instructions are disabled. Antigravity is also disabled by default because its CLI loads user tool-permission rules and has no safe/no-tools mode. Treat all three opt-ins as machine security policy, not per-call choices. Enable Copilot only through the installer switch `-EnableUnconfinedCopilotReviewer` (environment policy `MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER=1`), never from a task prompt.

For local LM Studio work, use the URL and optional default model reported by `doctor` or legacy `get_agent_status`; these are machine-local settings and must not be assumed from another PC. Same-PC installs normally use loopback, while a separate LM Studio host requires its configured HTTPS/authenticated endpoint or an approved tunnel. Never place machine-specific endpoints or API tokens in the public skill or repository. Use LM Studio as a read-only advisory reviewer, not as the coordinator. Select it explicitly in `run_agent` or `run_panel`, or use `ask_lm_studio`/`include_lm_studio=true` on legacy calls; do not add it to a default panel because local latency and availability vary. Keep large context sets bounded. The router must check that the requested model is advertised and must reject a response whose reported model differs from the request. If LM Studio is unavailable or times out, report that result and continue with other available evidence.

Context-file transfer is disabled until the machine installer records one or more narrow approved roots. Use an absolute `working_dir` inside an approved root and relative `context_files`; never broaden the roots to a user profile, drive, credential, or secrets directory merely to make a call succeed. A rejected path is a security boundary, so continue without that external context or ask the user/admin to approve a specific project root.

## Delegation Decision

When this skill is invoked for a nontrivial task, start grounded coordinator work immediately and delegate at least one meaningful subtask or independent review instead of merely considering delegation. Tool discovery and model availability checks must not become a prerequisite for repository inspection or coordinator progress. Increase coverage when at least one condition applies:

- The work spans multiple modules, platforms, or ownership areas.
- The code search space is broad and independent questions can be answered in parallel.
- The task has high regression risk, security risk, data-loss risk, or packaging/release risk.
- The user asks for review, architecture judgment, CI triage, PR feedback, or a second opinion.
- The implementation can be split into disjoint write scopes.

Skip delegation only when the task is small and purely mechanical, the user explicitly prohibits delegation, or no subordinate agent surface is available. If delegation is prohibited, unavailable, or rejected at runtime, continue under the current Codex coordinator and state the fallback without starting capability archaeology.

Native Codex sub-agents and external CLI agents have different entry criteria. Use native sub-agents for ordinary bounded parallel work when permitted. Run an external CLI automatically only when the user explicitly asks for that provider or when release, security, data-loss, authentication, payment, or similarly high-risk work clearly benefits from independent validation. Ask before broad or unusually long external execution. External CLI agents remain advisory and read-only; reject any write-capable mode for the active workspace.

## Purpose Routing

Classify each delegated brief as `implementation`, `review`, or `general` before dispatch. For an implementation or review brief, load exactly one corresponding purpose reference, once. General assignments load neither reference. Do not pre-load both references or re-read an unchanged reference unless context was compacted and the instructions are no longer available.

- For feature work, bug fixes, refactors, or implementation planning, read [references/implementation.md](references/implementation.md) and use its brief and result contract.
- For code review, regression analysis, test-gap review, release risk, or independent validation, read [references/review.md](references/review.md) and use its severity and evidence contract.
- For general research or comparison, keep the brief task-specific and include the same acceptance criteria for every agent being compared.

Keep these variants as references rather than separate automatically triggered skills so the coordinator, model, security, and validation policies have one source of truth.

## Workflow

1. Keep the current calling Codex session as coordinator. Record GPT-5.6 Sol only when the active product already selected or explicitly reports it; never infer or claim a coordinator-model switch from this skill.
2. Resolve the real target checkout before provider or model preparation. Verify its repository state, remote, relevant entry points, tests, and user-named deliverables enough to maintain the complete task model and write concrete prompts.
3. Begin useful coordinator work. Classify each assignment as implementation, review, or general; load exactly one corresponding purpose reference for implementation or review and neither reference for general work; then split work by bounded outcome. Include the exact question, relevant paths, non-goals, constraints, shared system-level acceptance criteria, subtask-specific criteria, evidence standard, read-only or patch-proposal policy, and expected output in every assignment.
4. For native Codex sub-agents, use the active `spawn_agent` schema directly and attempt the selected model once. Put `Target checkout: <absolute path>` in every brief, require all work to occur there, and explicitly forbid edits in an initial wrapper directory when it differs. Keep ownership clear; for writable children, assign disjoint files or modules and state that other agents may be editing the codebase.
5. Only when an external CLI or LM Studio assignment is ready to dispatch, run `doctor` (or the legacy status fallback) and any provider-specific model listing. Keep external agents advisory and non-writing, respect startup policy gates and allowed context roots, and ask for analysis, risks, alternatives, missed edge cases, or patch proposals rather than direct file edits.
6. Apply the native diagnostic circuit breaker: one selected-model attempt, at most one fallback for a coordinator-selected model, no environment forensics during project work, and no interruption to unrelated coordinator progress.
7. Supervise delegated work. Monitor completion, request missing evidence, redirect drift, and continue independent coordinator work without overlapping delegated write scopes.
8. Critically review every returned result. Accept only recommendations supported by repository evidence, tests, logs, or reproducible reasoning.
9. Resolve conflicts explicitly. Prefer local source-of-truth evidence and coordinator verification over agent consensus.
10. Integrate accepted work and validate the final result locally with targeted tests, builds, dry-runs, or manual inspection.
11. Report the synthesized conclusion with agent assignments, accepted or rejected findings, unresolved conflicts, requested-versus-observed model evidence when the tool envelope provides it, failed or timed-out agents, and validation evidence.

## Prompt Templates

Use this shape for read-only external reviews:

```text
Read-only review. Working directory: <path>.
Task: <specific question>.
Relevant files: <paths>.
Constraints: Do not edit files. Ground findings in file paths, line references, logs, or command output. Return: findings, risks, and concrete recommendations.
```

Use this shape for writable Codex sub-agents when permitted:

```text
You are not alone in the codebase. Do not revert edits made by others.
Target checkout: <absolute path>. Run every command, edit, and test there; do not work in an initial wrapper directory.
Own this scope only: <files/modules>.
Goal: <specific implementation or verification goal>.
Constraints: <tests, compatibility, style, no unrelated refactors>.
Return: changed files, validation run, remaining risks.
```

## Synthesis Standard

In the final answer, include only the useful coordination details:

- Agent coverage: which agents or sub-agents were used and for what.
- Evidence boundary: distinguish external-agent claims, coordinator-verified facts, and unresolved conflicts.
- Accepted findings: recommendations incorporated into the final result.
- Rejected findings: recommendations not used, with the reason.
- Validation evidence: tests, builds, checks, or source references used to confirm the result.

If an external agent times out or is unavailable, state that briefly and continue with the best available local verification.
