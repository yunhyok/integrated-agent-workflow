# Review Brief

Use this reference for code review, regression analysis, test-gap review, release risk, and independent validation.

## Brief

Give every reviewer the same acceptance criteria and include:

- Scope under review.
- Base branch, diff source, or exact files when known.
- Review priorities: correctness, security, data loss, regressions, tests, and maintainability.
- Requested provider model, when the user specified one.
- Read-only policy and authorized context boundary.
- Required output fields: severity, file or line reference, evidence, impact, suggested fix, and regression test.
- Evidence requirements for substantive findings. Runtime status, requested and observed models, model-match state, duration, and exit information come from the router or tool envelope, not reviewer prose.

## Required Result

Use one severity scale for every reviewer:

- `P0`: immediate release blocker with active compromise, unrecoverable data loss, or universally broken core behavior.
- `P1`: release blocker with a realistic security, correctness, data-loss, or core-workflow failure.
- `P2`: material but non-blocking defect, regression risk, or important test gap.
- `P3`: minor maintainability, clarity, or low-impact improvement.

Require findings in severity order. Reject vague concerns that lack a reproducible path, source reference, or concrete reasoning. Verify every material finding against the local source, diff, logs, or tests before presenting it as actionable. Attach authoritative runtime fields from the router or tool envelope; do not accept those transport facts from reviewer prose.

Report separately:

- External reviewer claims.
- Coordinator-verified findings.
- Rejected findings and why they were rejected.
- Unresolved conflicts or missing evidence.
- Checks actually run.

Treat partial panel results independently. A failed or timed-out reviewer does not invalidate usable results from another reviewer, but it also does not count as confirming a finding.
