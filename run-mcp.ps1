[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Stop-Launcher {
    param([Parameter(Mandatory = $true)][string]$Message)

    [Console]::Error.WriteLine("Integrated Agent Workflow: $Message")
    exit 2
}

if (-not $env:LOCALAPPDATA) {
    Stop-Launcher 'LOCALAPPDATA is unavailable, so the machine-local plugin configuration cannot be located.'
}

$configPath = Join-Path $env:LOCALAPPDATA 'OpenAI\multi-agent-router\plugin-config.json'
$managedNames = @(
    'MULTI_AGENT_LM_STUDIO_BASE_URL',
    'MULTI_AGENT_LM_STUDIO_MODEL',
    'MULTI_AGENT_LM_STUDIO_MAX_TOKENS',
    'MULTI_AGENT_LM_STUDIO_REASONING_EFFORT',
    'MULTI_AGENT_LM_STUDIO_ALLOW_INSECURE_REMOTE',
    'MULTI_AGENT_LM_STUDIO_ALLOW_UNAUTHENTICATED_REMOTE',
    'MULTI_AGENT_MAX_CHARS',
    'MULTI_AGENT_TIMEOUT_SEC',
    'MULTI_AGENT_RUNTIME_DIR',
    'MULTI_AGENT_ALLOWED_ROOTS_JSON',
    'MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER',
    'MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER',
    'MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER'
)

if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    Stop-Launcher "the machine-local plugin configuration is missing. Run '.\install.ps1 -PluginMode' from the protected source checkout, then restart Codex."
}
try {
    $config = [IO.File]::ReadAllText($configPath) | ConvertFrom-Json
}
catch {
    Stop-Launcher "the machine-local plugin configuration is invalid JSON: $($_.Exception.Message)"
}

if ($null -eq $config -or
    $null -eq $config.PSObject.Properties['schemaVersion'] -or
    [int]$config.schemaVersion -ne 1 -or
    $null -eq $config.PSObject.Properties['pythonPath'] -or
    $null -eq $config.PSObject.Properties['routerPath'] -or
    $null -eq $config.PSObject.Properties['environment']) {
    Stop-Launcher "the machine-local plugin configuration has an unsupported schema. Rerun '.\install.ps1 -PluginMode' from the protected source checkout."
}

$pythonPath = $config.pythonPath
$routerPath = $config.routerPath
if ($pythonPath -isnot [string] -or -not $pythonPath.Trim() -or
    $routerPath -isnot [string] -or -not $routerPath.Trim() -or
    -not [IO.Path]::IsPathRooted($pythonPath) -or
    -not [IO.Path]::IsPathRooted($routerPath) -or
    $pythonPath.StartsWith('\\') -or $routerPath.StartsWith('\\')) {
    Stop-Launcher 'the configured Python and router paths must be absolute local paths.'
}

$pythonPath = [IO.Path]::GetFullPath($pythonPath)
$routerPath = [IO.Path]::GetFullPath($routerPath)
$sourceRoot = Split-Path -Parent $routerPath
$expectedPythonPath = [IO.Path]::GetFullPath(
    (Join-Path $sourceRoot '.venv\Scripts\python.exe')
)
if (-not $pythonPath.Equals($expectedPythonPath, [StringComparison]::OrdinalIgnoreCase)) {
    Stop-Launcher 'the configured Python path is not the private environment beside the router source.'
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Stop-Launcher "the configured private Python environment is missing. Rerun '.\install.ps1 -PluginMode' from the protected source checkout."
}
if (-not (Test-Path -LiteralPath $routerPath -PathType Leaf)) {
    Stop-Launcher "the configured router source is missing. Rerun '.\install.ps1 -PluginMode' from the protected source checkout."
}

$environmentConfig = $config.environment
if ($null -eq $environmentConfig) {
    Stop-Launcher 'the machine-local plugin environment is missing.'
}
foreach ($name in $managedNames) {
    $property = $environmentConfig.PSObject.Properties[$name]
    if ($null -eq $property -or $null -eq $property.Value) {
        continue
    }
    if ($property.Value -isnot [string]) {
        Stop-Launcher "the machine-local value '$name' must be a string."
    }
    if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
        [Environment]::SetEnvironmentVariable($name, [string]$property.Value, 'Process')
    }
}

& $pythonPath $routerPath
exit $LASTEXITCODE
