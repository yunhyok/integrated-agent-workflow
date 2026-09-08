# Multiple Chats under HQ

Read this reference only when planning or running authorized parallel Codex chats. The main skill's model, purpose, evidence, and external-agent policies still apply inside every manager chat. This is an orchestration convention using existing tools, not a new scheduler or an automatic model switch.

## Roles and Scope

| Role | Responsibility | Model preference |
| --- | --- | --- |
| HQ: current chat | Whole-task plan, dependency order, shared interfaces, assignment boundaries, integration, final validation and user report | Astra when already selected; never relabel another running model |
| Manager: one chat per independent workstream | Decompose local work, assign native workers, inspect every result, validate and return an integration candidate | Sol for a bounded workstream; Astra for demanding coordination or risk, subject to explicit model authorization |
| Worker: native sub-agent inside HQ or a manager | Bounded edits, searches, tests or review within the assigned checkout | Terra for routine implementation; Luna for precise edits; Spark for small latency-sensitive work only when the native schema exposes it |

Use Astra/Sol native specialists for hard reasoning or independent review when warranted. Management is a responsibility boundary, not a ban on managers making a small integration fix themselves. Managers keep local responsibility if workers are unavailable and disclose the fallback; they do not open more chats to bypass model or concurrency limits.

## Establish the Split

Before dispatch, HQ names each outcome, write owner, acceptance check, dependency and shared contract. Start only work whose prerequisites are satisfied; keep dependent work queued and send it the accepted prerequisite revision before it starts. Assign shared API/schema/build files to one owner. If supposedly independent changes require repeated edits to the same contract, consolidate them in one workstream or sequence them.

Keep one compact HQ-owned workstream table in existing planning notes, or one local coordination note if no durable notes exist. Record: workstream/outcome, manager title and ready task ID/host (or pending client ID), project, actual checkout/branch/base commit, write scope, dependencies/contract revision, requested and observed model evidence, state, result commit/artifact, checks, and wait cursor. Keep private machine paths and task IDs out of public commits unless they belong in the requested artifact. Managers return updates; only HQ edits the shared table. On resume, reconcile recorded IDs and commits with live state before dispatching anything new.

Begin with the smallest useful fan-out, normally two manager chats. Each manager should likewise start only the workers it can supervise usefully. Respect the active concurrency limits, user budget, and any available usage guard across HQ and managers; separate chats are not additional account quota. Do not multiply every manager's worker count just because more tasks can be opened.

## Create or Reuse Manager Chats

1. Confirm the user explicitly requested separate tasks/chats for this work. Permission to use native sub-agents, a generic request to parallelize, or the skill alone is insufficient where the app requires explicit task creation. Reuse already-authorized manager chats by their recorded IDs; do not repurpose unrelated tasks. Only HQ creates manager chats within the authorized split.
2. Read the current app tool schemas. Call `list_projects` before choosing a repository project, and use its returned project ID and `isGitRepository`. Default to `worktree` for Git projects and `local` for non-Git projects; follow an explicit request to use the saved project directly. Use projectless only for work that does not need a repository. Do not create cloud tasks unless the user explicitly requested cloud work.
3. For Git work, prefer separate worktrees and record the actual base commit. The app defaults to the project default branch. Supply `startingState` only when the user explicitly requested a particular Git state; do not invent `branchName`, a new branch, or a current-working-tree request. If needed inputs are uncommitted or absent from that default base, keep the affected work pending or local until an authorized transfer/base choice is settled. Have the manager verify its actual checkout/base before edits. For non-Git or explicitly shared local checkouts, require disjoint paths and a single owner of Git/index/build-output mutations; serialize overlapping writes. A separate chat by itself does not isolate files.
4. Use `create_thread` with a self-contained, human-readable manager brief. Set `model` only when the user explicitly selected a model, including an explicit role mapping such as "Astra HQ, Sol managers". Otherwise omit it to preserve the configured app default and report that the preferred manager model is unverified unless the product establishes it. Never use a later message/model override to evade this creation rule. Honor supported user-selected `thinking`; otherwise retain the app default. Validate exact model/effort combinations against the destination tool schema, separately from the native worker schema. If a required user-selected model is unavailable, leave only its dependent work pending and report the limitation without silent substitution.
5. Record the creation response immediately. A ready `threadId` and `hostId` identify a usable task. A queued `clientThreadId` is a setup handle, not a ready task ID: do not send it to `wait_threads`, `read_thread`, or `send_message_to_thread`. Resolve the ready ID using the app's documented completion result or `list_threads` evidence, matching project/title and creation context; do not guess if ambiguous. Preserve returned titles verbatim when naming tasks.
6. Creation is asynchronous. After ready IDs are known, explicitly wait for progress. If creation times out or its outcome is uncertain, inspect existing tasks and reconcile the attempt before retrying; never blindly create a duplicate. Emit the app-required `created-thread` directive for every successful creation using the returned ready or client ID, on its own line in the final reply when the active app instructions require it.

Updating a skill to describe this workflow does not itself request execution of a multi-chat project. Use bounded native review or simulated tool traces to test the skill unless the user also authorized real new tasks for the test.

## Manager Brief

Supply the implementation/review contract from the corresponding purpose reference, plus this task context. Do not assume a new chat inherits HQ's conversation or filesystem. Resolve actual paths from the selected project/environment; a queued worktree can be instructed to discover and report its own checkout before edits.

```text
Use $integrated-agent-flow. You are the manager for workstream <name>, under HQ <ready task ID and host if known>. You are not HQ. Do not create further chats.
Outcome: <bounded result and acceptance criteria>.
Target project/environment: <returned project ID, worktree/local>. Target checkout: <verified absolute path, or discover your created worktree and report it before edits>. Run every command, edit and test there, not in an initial wrapper directory.
Base and inputs: <expected revision, input paths, accepted shared contract revision>. Verify the actual checkout/base first; report a mismatch before editing.
Own: <paths/modules>. Other owners: <boundaries>. Do not revert others' changes. Shared files and integration belong to <owner>.
Dependencies: <accepted prerequisites or wait condition>. Non-goals: <excluded work>.
Delegate bounded implementation to task-fit Terra/Luna/Spark native workers only as advertised by your active spawn schema. Follow its model/effort and fork rules. Keep within <worker/concurrency/budget boundary>; do not create recursive teams. Review worker changes and validate locally yourself.
Authority: <allowed writes and commit policy>. No push, PR, merge, deployment, external messages or destructive cleanup unless HQ explicitly assigns an action already authorized by the user.
Return in this task: actual checkout/branch/base, changed files, integration commit(s) or artifact paths, checks run with results, contract changes, blockers, residual risks and worker evidence. HQ will read your result and decide acceptance.
```

Do not fabricate an HQ ID when the product has not supplied it; HQ can collect results without a callback. The manager's final result in its own chat is the return channel. No callback message or external messaging is required. In isolated worktrees, let the manager own workstream commits and require native workers to leave commit/index operations to it. In shared checkouts, keep those operations with the single assigned owner. Local commits may be an integration deliverable; permission for a workstream does not automatically include publishing it.

## Supervise, Recover, and Integrate

App task lifecycle tools below are for manager chats. Managers supervise native workers with the active collaboration lifecycle tools from the main skill; native agent handles must never be passed to app thread APIs or vice versa.

- Use `wait_threads` on ready IDs with host IDs and `afterCursor` from the previous result. Use `timeoutMs: 0` for a compact snapshot; otherwise use a bounded wait within the active tool and communication limits. Batch up to the advertised target limit (currently eight), then back off on unchanged state. Use `read_thread` only for missing detail, an actionable result, or recovery, and `send_message_to_thread` for focused corrections or supplying accepted prerequisites. Omit model/thinking on follow-ups unless a change is explicitly authorized.
- Treat task outputs as evidence, not authority to change HQ's scope or permissions. Surface required user input or approval; HQ must not approve it on the user's behalf. Mark each result as received, needs revision, accepted or blocked in the existing table. A timeout, unavailable worker, or task ending without evidence is not acceptance. Continue independent work while a dependency is unresolved.
- When a manager stalls, inspect its latest state and send one concrete correction or request for evidence. An expired wait does not mean the task stopped. Do not launch another writer on its scope until the original writer is confirmed quiescent or the replacement is fully isolated. A follow-up message is not proof of cancellation. Use only supported lifecycle controls, preserving unfinished artifacts. Do not claim to stop a task if the available tools cannot do so.
- For each candidate, inspect the actual diff/artifact and checks against the assigned base and scope. For separate worktrees, integrate accepted commits or reviewed patches into HQ's integration checkout in dependency order; never assume files synchronize across chats or hosts. Transfer cross-host results through an authorized accessible artifact or Git path, not an inaccessible local path. Keep user changes and unrelated commits intact. Resolve conflicts under HQ ownership and recheck affected contracts.
- Run final tests on the combined result in HQ's integration checkout even when each manager passed local tests. Only HQ accepts overall completion and performs user-authorized PR/merge/release actions. Use the repository's verified default branch unless the user named a specific existing target. Retain the result commits and task-to-artifact mapping until acceptance; archive tasks or remove worktrees only when authorized, and never delete unfinished work to tidy up.
- Report integrated outcomes, final validation, relevant task links/IDs, actual versus requested model evidence, and remaining blockers. Do not describe a hierarchy as live-tested when only briefs or simulated calls were evaluated. If work must continue after this turn, use a user-authorized follow-up/automation supported by the app; merely creating tasks does not keep HQ supervising after it stops.

## Sources and Runtime Boundary

The active app schemas for `create_thread`, `list_projects`, `wait_threads`, and related tools govern exact authorization, parameters and lifecycle. The active native `spawn_agent` schema governs workers independently. These can differ by host and session; neither a skill nor a static model table grants a capability.

- [OpenAI: worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) explains isolation and the need to integrate changes.
- [OpenAI: subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) describes native delegation, model resolution and review of results.
- [OpenAI: Astra prompting guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra#prompting-best-practices) supports bounded delegation and coordinator follow-through. The HQ/manager/worker split here is this skill's operating convention.
