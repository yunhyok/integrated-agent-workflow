# Integrated Agent Workflow v0.5.0 Doctor

Doctor checks whether local external agent CLIs and the configured LM Studio server are ready.

It reports:

- Plugin name and version.
- OpenAI Codex, Claude, Copilot, and Antigravity binary availability.
- LM Studio endpoint reachability, selectable model IDs, and configured-model availability.
- Windows native executable discovery when the Codex app has a stale PATH.
- Version output when available.
- Login guidance when an agent appears unavailable or unauthenticated.
- Non-secret cache path.

Doctor output is advisory. A later run can still fail if a CLI session expires, the LM Studio server stops, or the loaded model is evicted after doctor runs.
