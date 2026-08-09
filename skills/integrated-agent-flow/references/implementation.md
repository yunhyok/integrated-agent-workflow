# Implementation Brief

Use this reference for feature work, bug fixes, refactors, and implementation planning.

## Brief

Give every assigned agent the same system-level acceptance criteria, then add criteria specific to that agent's bounded subtask. Include:

- Goal and required behavior.
- Relevant files, modules, or search targets.
- User constraints and applicable repository instructions.
- Explicit non-goals.
- Test and verification expectations.
- Requested provider model, when the user specified one.
- Read-only or patch-proposal policy for external agents.
- Evidence requirements for the substantive result. Runtime status, requested and observed models, model-match state, duration, and exit information come from the router or tool envelope, not the model's prose.

Assign writable native Codex sub-agents only when policy permits it and give each one a disjoint ownership boundary. Keep external CLI and LM Studio agents advisory; ask them for a patch proposal or exact change description, not direct workspace edits.

## Required Result

Require each agent to return:

- Proposed approach.
- Files or modules affected.
- Patch proposal or exact change summary.
- Tests expected or actually run, clearly distinguished.
- Risks, assumptions, and missing context.

Attach authoritative runtime fields from the router or tool envelope. Do not ask the model to self-report those transport facts or accept them from its prose. Record an exact transport-observed model match as confirmed, a different observed model as mismatch, and absent transport evidence as unverified. Keep expected tests separate from tests the coordinator actually ran.

Review and verify the proposal before applying or adapting any change.
