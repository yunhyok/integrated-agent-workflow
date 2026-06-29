# Integrated Agent Workflow v0.1.0 Doctor

Doctor checks whether local external agent CLIs are ready.

It reports:

- Plugin name and version.
- Claude, Copilot, and Antigravity binary availability.
- Version output when available.
- Login guidance when an agent appears unavailable or unauthenticated.
- Non-secret cache path.

Doctor output is advisory. A later run can still fail if a CLI session expires after doctor runs.
