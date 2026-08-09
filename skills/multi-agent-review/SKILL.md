---
name: multi-agent-review
description: Use with multi-agent-orchestration for code review, regression analysis, test gap review, release risk review, or independent validation.
---

# Multi-Agent Review Preset

Load multi-agent-orchestration first. This skill only supplies the review brief structure and severity focus.

## Review Brief

Create a review brief with:

- Scope under review.
- Base branch or diff source when known.
- Files or modules to inspect.
- Review priorities: correctness, security, data loss, regressions, tests, maintainability.
- Requested model map when the user specified provider models for cost, latency, or capability control.
- Output format with severity, file reference, evidence, and suggested fix.

## Result Requirements

Ask each external agent to return:

- Findings ordered by severity.
- File and line references when available.
- Why each issue matters.
- Suggested fix.
- Tests that would catch the issue.

Codex must verify each finding before presenting it as actionable.
