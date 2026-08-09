# Integrated Agent Workflow v0.6.0

A Windows-first Codex skill and hardened local MCP router for coordinated,
model-aware implementation and review. Codex native sub-agents handle ordinary
bounded work; the optional Python MCP router adds advisory opinions from Claude
Code, GitHub Copilot CLI, Antigravity CLI, LM Studio, and an explicitly opted-in
Codex CLI reviewer.

The calling Codex session remains the coordinator. Claude and Copilot run with
their tools disabled or reduced to the isolated request file. LM Studio receives
only the prompt and explicitly allowed context. Codex and Antigravity CLI review
tools are disabled by default because their read capabilities cannot be fully
confined independently of local user configuration.

## Architecture

The repository intentionally exposes one auto-trigger skill,
`integrated-agent-flow`, with purpose-specific implementation and review
references loaded only when needed. This keeps orchestration, safety, model
reporting, and acceptance-criteria rules in one source of truth without losing
the useful detail of the former three-skill layout.

The plugin MCP entry starts `run-mcp.ps1`, which loads non-secret settings from
a protected machine-local JSON file and launches the repository's private
Python environment. The legacy TypeScript MCP server was removed so there is
only one runtime and one security policy to validate.

## Tools

- `doctor`: structured availability and active security-policy diagnostics
- `list_lmstudio_models`: merged LM Studio native and OpenAI-compatible model
  metadata
- `run_agent`: one policy-confined adviser with an explicit purpose,
  acceptance criteria, model map, and write policy
- `run_panel`: a genuinely concurrent panel, defaulting to the confined Claude
  and Copilot advisers
- `ask_codex` (disabled unless the installer records an explicit risk opt-in)
- `ask_claude`
- `ask_copilot`
- `ask_antigravity` (disabled unless the installer records an explicit risk opt-in)
- `ask_lm_studio`
- `collect_reviews`
- `get_agent_status`
- `list_agent_models`

`run_agent` and `run_panel` are the preferred integration interface. Their JSON
evidence records include `schemaVersion`, `agentId`, `requestedModel`,
`observedModels`, `modelMatch`, `status`, `durationMs`, `exitCode`, result text,
and a redacted error field. `modelMatch` is `confirmed`, `mismatch`, or
`unverified`; an unreported model is never presented as confirmed. Panel results
also include an aggregate status and actual wall-clock duration. Direct external
writes are rejected: `write_policy` accepts only `read_only` or
`patch_proposal`, and the latter requests patch text without granting filesystem
write access.

Each `ask_*` tool accepts an optional `model`. `collect_reviews` accepts a
separate model override for every reviewer. Results use the form
`Agent (model: actual-model)` whenever the CLI or API reports the served model.
Claude Code accepts a model override but does not expose a reliable catalog, so
the router reports that limitation instead of inventing model names.

When Claude is selected for difficult multi-file work, architecture, hard
debugging, release-risk review, security review, or other high-risk validation,
the coordinator skill requests the exact model ID `claude-opus-5` unless the
user selected another Claude model. It never uses the `opus` alias for Opus 5
and never silently substitutes another model after an exact request fails.

## Requirements

- Windows PowerShell 5.1 or PowerShell 7
- Python 3.11 or newer
- Codex CLI 0.147.0 or newer, installed and signed in
- Any optional reviewer CLIs you want to use:
  - Claude Code
  - GitHub Copilot CLI
  - Antigravity CLI
- Sign in separately to every optional reviewer CLI you enable
- LM Studio 0.4.8 or newer for `reasoning_effort`; older servers can omit it

`doctor` reports a CLI as `available` when its executable responds to a version
probe. It does not perform an authenticated provider request; `run_agent` or the
legacy `ask_*` call reports login or account failures when that reviewer is first
used.

## Install on each computer

Clone the repository into a directory private to your Windows account (for
example, a project folder under your user profile), then choose exactly one
installation mode.

### Standalone MCP registration

Open PowerShell in the checkout and run:

```powershell
.\install.ps1
```

This mode registers the `multi_agent` MCP server in that computer's Codex
configuration. Use it when the repository is not being loaded as a Codex
plugin.

### Plugin runtime preparation

This repository contains a valid Codex plugin source bundle, but it is not a
marketplace catalog. Direct clones should normally use standalone registration.
If an administrator or an existing marketplace loads the bundle through
`.codex-plugin/plugin.json`, first retain a protected source checkout and prepare
its private Python environment and machine-local configuration without creating
a second global MCP registration:

```powershell
.\install.ps1 -PluginMode
```

The plugin manifest's `.mcp.json` launches `run-mcp.ps1`. Plugin caches do not
need to contain `.venv`: the launcher reads the protected source checkout's
absolute Python and router paths from the machine-local configuration written by
`-PluginMode`. Keep that checkout at the recorded path. A clean clone needs this
one-time preparation because Python dependencies and computer-specific paths are
intentionally not committed. Rerun the same command after moving the checkout or
after dependency changes. If the plugin was already loaded, restart Codex after
preparation so its STDIO server is recreated.

Start the LM Studio server before installation so its endpoint and model can be
verified. To register an intentionally offline server, use
`-SkipLmStudioProbe`; this explicitly defers endpoint and model validation.

Both modes create `.venv`, enforce Python 3.11+, install the pinned MCP
dependency, and restrict the checkout and private runtime ACLs to the installing
user, SYSTEM, and Administrators. Standalone mode additionally registers this
checkout. A same-checkout standalone update changes only installer-managed keys
in place, preserving custom command overrides, extra environment variables,
tool filters, and unrelated Codex configuration. Rebinding a same-named global
registration from another checkout requires `-ForceRebind` and never inherits
that foreign endpoint. The completed standalone registration is read back and
verified. Restart Codex after installation.

The installer also rejects a checkout whose ancestor ACL lets another local
SID delete, rename, or take ownership of the path. A protected child directory
alone cannot prevent replacement through a permissive ancestor: Windows permits
delete/rename when the relevant object or parent grants delete rights. The
`-AllowUnsafeCheckoutParent` override is intended only for ephemeral CI test
checkouts, not a persistent MCP installation. See Microsoft's
[file deletion permission rules](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile).

Preview local changes without probing LM Studio or modifying configuration:

```powershell
.\install.ps1 -WhatIf
.\install.ps1 -PluginMode -WhatIf
```

To select a model explicitly:

```powershell
.\install.ps1 `
  -LmStudioBaseUrl 'http://127.0.0.1:1234' `
  -LmStudioModel 'publisher/model-id'
```

Add `-PluginMode` to the same command when preparing the plugin runtime.

Context-file transfer is disabled by default. Approve only a specific project
root whose files may be sent to the selected reviewer:

```powershell
.\install.ps1 -AllowedRoot 'C:\path\to\approved-project'
```

Pass a PowerShell string array to `-AllowedRoot` when several independent roots
are required. Files outside these machine-local roots are rejected before an
external process or HTTP request starts. Do not approve a profile, home, drive,
credential, or secrets directory.

If LM Studio is running and advertises exactly one LLM, the installer selects
that model. With zero or multiple advertised LLMs, the default remains unset;
pass `model=...` to `ask_lm_studio` or rerun the installer with
`-LmStudioModel`. An explicitly selected model must be advertised, including
when the server reports an empty LLM list.

## LM Studio addresses are machine-local configuration

No computer-specific LM Studio URL, model ID, or API token is stored in this
repository. Standalone mode writes the URL and optional model only to that
computer's `~/.codex/config.toml` MCP entry. Plugin mode writes non-secret
settings to
`%LOCALAPPDATA%\OpenAI\multi-agent-router\plugin-config.json`; the API token
remains in `LM_API_TOKEN` or `MULTI_AGENT_LM_STUDIO_API_KEY` and is never written
to that file. Plugin mode also records the retained source checkout's absolute
Python and router paths only in this protected machine-local file, never in the
repository. Codex documents `env` as the map of environment variables
forwarded to an STDIO MCP server and supports the same values through
`codex mcp add --env KEY=VALUE`.

Use the address that matches each computer:

| Scenario | Example |
|---|---|
| LM Studio on the same computer | `http://127.0.0.1:1234` |
| Same computer, custom port | `http://127.0.0.1:3000` |
| HTTPS endpoint on another trusted computer | `https://lmstudio.example.internal` |
| Local VPN/tunnel endpoint | The loopback URL exposed by the tunnel |

When LM Studio and Codex run on the same computer, `127.0.0.1` is portable and
does not change from PC to PC. A hostname or LAN IP is needed only when the
router connects to LM Studio on a different computer.

The router reads these settings when its MCP process starts, in this order:

- Base URL: `MULTI_AGENT_LM_STUDIO_BASE_URL`, then
  `http://127.0.0.1:1234`
- Model: per-call `model`, then `MULTI_AGENT_LM_STUDIO_MODEL`, then unset
- Token: `MULTI_AGENT_LM_STUDIO_API_KEY`, then `LM_API_TOKEN`, then unset
- Generation options: per-call values, then machine-local environment values,
  then router defaults

After changing any machine-local setting, restart Codex so the STDIO MCP server
is recreated.

### Remote LM Studio security

LM Studio warns that binding anywhere other than `127.0.0.1` exposes the server
beyond localhost and recommends authentication. The router therefore applies
these defaults:

- unauthenticated HTTP is allowed only on loopback;
- a remote endpoint requires HTTPS and an API token;
- `0.0.0.0` and `[::]` are rejected as client destinations;
- remote plain HTTP requires the explicit installer switch
  `-AllowInsecureRemoteLmStudio`;
- remote use without authentication requires the explicit installer switch
  `-AllowUnauthenticatedRemoteLmStudio`.

For a remote server, enable **Require Authentication** in LM Studio and store a
restricted token as a user environment variable before installing:

```powershell
[Environment]::SetEnvironmentVariable('LM_API_TOKEN', '<token>', 'User')
```

Then restart Codex and install with the remote HTTPS address. The installer
forwards the variable name, not the token value, in Codex configuration. The
router also removes LM Studio credentials from environments passed to CLI
reviewers.

If HTTPS is not available, prefer an approved VPN or local port tunnel. Plain
HTTP sends prompts, source context, and bearer tokens without transport
encryption; the opt-in switch does not make that connection secure. Do not
publish LM Studio's port directly to the internet.

References:

- [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp)
- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [LM Studio: serve on a local network](https://lmstudio.ai/docs/developer/core/server/serve-on-network)
- [LM Studio authentication](https://lmstudio.ai/docs/developer/core/authentication)

## Integrated Agent Flow skill and GPT-5.6 Luna

The distributable skill is under `skills/integrated-agent-flow`. Plugin-managed
installs should activate the complete v0.6.0 plugin rather than copy the skill
separately. For a manual local skill install, archive the previous copy and the
three v0.5 skill folders outside the active skills directory, then install a
clean copy:

```powershell
$codexRoot = if ($env:CODEX_HOME) {
  [IO.Path]::GetFullPath($env:CODEX_HOME)
} else {
  Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
}
$skillsRoot = Join-Path $codexRoot 'skills'
$backupRoot = Join-Path $codexRoot (
  'skill-backups\integrated-agent-workflow-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
)
$skillNamesToArchive = @(
  'integrated-agent-flow',
  'multi-agent-orchestration',
  'multi-agent-implementation',
  'multi-agent-review'
)
$existingSkillPaths = @(
  $skillNamesToArchive |
    ForEach-Object { Join-Path $skillsRoot $_ } |
    Where-Object { Test-Path -LiteralPath $_ -PathType Container }
)
if ($existingSkillPaths.Count -gt 0) {
  New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
  foreach ($existingSkillPath in $existingSkillPaths) {
    Move-Item -LiteralPath $existingSkillPath -Destination $backupRoot
  }
}
New-Item -ItemType Directory -Path $skillsRoot -Force | Out-Null
$targetSkillPath = Join-Path $skillsRoot 'integrated-agent-flow'
Copy-Item -LiteralPath '.\skills\integrated-agent-flow' `
  -Destination $targetSkillPath -Recurse
```

The archive is recoverable under `~/.codex/skill-backups`. Do not leave the old
three folders under `~/.codex/skills`: their overlapping auto-trigger metadata
can activate alongside v0.6.0. Fully restart Codex after changing active skills.

Some Codex catalogs currently advertise `gpt-5.6-luna` as a v1 child model,
which makes `spawn_agent` reject it even though the model itself is available.
This repository includes an explicit local compatibility workaround:

```powershell
.\skills\integrated-agent-flow\scripts\Enable-LunaV2.ps1
```

The script requires Codex CLI 0.147.0+, leaves `models_cache.json` untouched,
backs up existing configuration, generates `models-luna-v2.json` from the
current PC's cache, changes only Luna's `multi_agent_version` to `v2`, writes
`model_catalog_json` at TOML top level, and verifies both strict configuration
and the effective catalog. Fully restart Codex afterward. Rerun the script
after a Codex/model-catalog update to refresh the override from the latest
cache. Never commit either generated catalog or personal `config.toml`.

`model_catalog_json` is a documented startup option, but the Luna field change
is a local workaround rather than a public API guarantee. Remove the top-level
setting or restore the timestamped backup to disable it. See the
[Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
and [GPT-5.6 Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

## Review context and privacy

For useful reviews, first configure a narrow `-AllowedRoot`, then pass concrete
relative files with `working_dir` and `context_files`. `working_dir` must be an
absolute directory inside an approved root; each context entry must be relative
to it. Parent/sibling escapes, absolute file arguments, filesystem roots, UNC
roots, and reparse-point paths are rejected before a reviewer starts. The
selected file contents are embedded in the external request, so an approved
root is a data-transfer trust boundary—not merely a path convenience. Only
approve and pass files that the selected service or remote LM Studio may receive.
The `prompt` text itself is also sent as supplied; do not place credentials or
unapproved local paths in it.

Large prompts are temporarily written under the private machine-local runtime
directory (by default `%LOCALAPPDATA%\OpenAI\multi-agent-router\prompts`) for
CLIs that cannot reliably accept long command-line input on Windows. Empty
isolated review working directories are created under the protected checkout's
`.tmp\reviews`. The router deletes both after each call. A process crash can
leave temporary data behind, so clear stale runtime prompts before diagnostics,
sharing, or archiving.

Child processes receive a minimal OS environment plus only the authentication
variables relevant to that reviewer (for example, `OPENAI_API_KEY` for Codex or
`ANTHROPIC_API_KEY` for Claude). LM Studio tokens and unrelated secrets are not
forwarded. Antigravity may keep its own CLI transcript under `~/.gemini`; use
its retention controls when prompts or selected files are sensitive.

### External reviewer risk opt-ins

The separate `ask_codex` CLI reviewer is startup-policy gated. Its read-only
sandbox prevents edits, but its shell can read other files accessible to the
same Windows account, even when launched from an isolated directory. Therefore
it is not a context-files-only boundary and is disabled on a fresh install.

Enable it only after accepting that prompts or prompt injection could cause
user-readable local files to be sent to OpenAI:

```powershell
.\install.ps1 -EnableUnconfinedCodexReviewer
```

Add `-PluginMode` when the plugin runtime is the selected installation mode.

This is a machine-local startup setting; restart Codex after changing it.
Prefer Codex's native child-agent orchestration when that read scope is not
acceptable.

GitHub Copilot CLI is gated separately because it discovers personal skills
and other profile-level customization from the Windows account even when its
built-in MCPs and custom instructions are disabled. It is therefore also
disabled on a fresh install. Enable it only after accepting that prompts or
prompt injection could expose profile metadata or other user-readable local
content to GitHub Copilot:

```powershell
.\install.ps1 -EnableUnconfinedCopilotReviewer
```

Add `-PluginMode` when the plugin runtime is the selected installation mode.
This is a machine-local startup setting; restart Codex after changing it.

Antigravity is gated separately because its CLI has no no-tools/safe-mode switch
and loads user permission rules. Its `--sandbox` option describes terminal
restrictions, not a complete read boundary. Enable it only after auditing those
rules and accepting the same external-file disclosure class:

```powershell
.\install.ps1 -EnableUnconfinedAntigravityReviewer
```

Add `-PluginMode` when the plugin runtime is the selected installation mode.

Example request:

```text
Use collect_reviews with working_dir="C:\path\to\repo",
context_files=["src\main.py", "README.md"], and include_lm_studio=true.
Ask each selected reviewer for one concrete risk and one improvement.
```

## Configuration variables

- `MULTI_AGENT_CODEX_CMD`
- `MULTI_AGENT_CLAUDE_CMD`
- `MULTI_AGENT_COPILOT_CMD`
- `MULTI_AGENT_ANTIGRAVITY_CMD`
- `MULTI_AGENT_ANTIGRAVITY_MAX_PROMPT_CHARS`
- `MULTI_AGENT_ALLOWED_ROOTS_JSON`
- `MULTI_AGENT_RUNTIME_DIR`
- `MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER`
- `MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER`
- `MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER`
- `MULTI_AGENT_LM_STUDIO_BASE_URL`
- `MULTI_AGENT_LM_STUDIO_MODEL`
- `MULTI_AGENT_LM_STUDIO_API_KEY` or `LM_API_TOKEN`
- `MULTI_AGENT_LM_STUDIO_MAX_TOKENS`
- `MULTI_AGENT_LM_STUDIO_REASONING_EFFORT`
- `MULTI_AGENT_LM_STUDIO_ALLOW_INSECURE_REMOTE`
- `MULTI_AGENT_LM_STUDIO_ALLOW_UNAUTHENTICATED_REMOTE`
- `MULTI_AGENT_TIMEOUT_SEC`
- `MULTI_AGENT_MAX_CHARS`
- `MULTI_AGENT_MAX_FILE_CHARS`

`collect_reviews` keeps LM Studio and Antigravity opt-in. Set
`include_lm_studio=true` or `include_antigravity=true` only when that reviewer
should join; Antigravity still requires its startup policy switch.

## Verify

```powershell
# Standalone mode only
codex mcp get multi_agent --json

# Plugin mode only
Test-Path "$env:LOCALAPPDATA\OpenAI\multi-agent-router\plugin-config.json"

# Both modes
Invoke-RestMethod http://127.0.0.1:1234/api/v1/models
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
```

Open a new Codex task after router code, configuration, or tool-schema changes.

## Update

Pull the latest source and rerun `install.ps1` with the same installation mode.
Standalone mode replaces only installer-managed fields for the named local
registration and keeps custom and unrelated Codex configuration intact. Plugin
mode refreshes its private environment and protected machine-local JSON without
creating or changing a global MCP registration.

If the skill was copied manually, rerun the clean-copy migration in
**Integrated Agent Flow skill and GPT-5.6 Luna**. If Codex loads the repository
as a plugin, activate the complete v0.6.0 bundle and verify that
`integrated-agent-flow` is the only skill exposed by this plugin; do not overlay
the v0.6.0 files onto an active v0.5.0 cache directory.

## Uninstall

Remove this checkout's MCP registration without deleting source or `.venv`:

```powershell
.\uninstall.ps1
```

Plugin mode creates no global registration. To stop using it, remove or disable
the plugin through the Codex plugin workflow. Its non-secret machine-local JSON
is retained so a later reinstall can preserve that computer's settings.

## License

No open-source license has been selected. Public repository visibility alone
does not grant permission to copy, modify, or redistribute the code.
