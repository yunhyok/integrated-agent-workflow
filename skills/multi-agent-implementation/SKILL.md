---
name: multi-agent-implementation
description: Use with multi-agent-orchestration for feature work, bug fixes, refactors, or implementation planning that benefits from OpenAI Codex, Claude, Copilot, or Antigravity input.
---

# Multi-Agent Implementation Preset

Load multi-agent-orchestration first. This skill only supplies the implementation brief structure and verification focus.

## Implementation Brief

Create an implementation brief with:

- Goal.
- Relevant files or search targets.
- Constraints from the user and repository instructions.
- Required behavior.
- Non-goals.
- Test expectations.
- Requested model map when the user specified provider models for cost, latency, or capability control.
- Whether the external agent may propose a patch or must stay read-only.

Prefer patch proposals over direct writes. Direct writes require a git worktree or temporary copy.

## Result Requirements

Ask each external agent to return:

- Proposed approach.
- Files it would change.
- Patch or exact change summary.
- Tests it expects to pass.
- Risks and assumptions.

Codex must review the proposal before applying or adapting any change.
