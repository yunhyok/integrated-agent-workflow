[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Equal {
    param($Actual, $Expected, [string]$Label)

    if ($Actual -ne $Expected) {
        throw "$Label mismatch. Expected '$Expected', got '$Actual'."
    }
}

function Invoke-Launcher {
    param(
        [Parameter(Mandatory = $true)][string]$PowerShellPath,
        [Parameter(Mandatory = $true)][string]$LauncherPath
    )

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $PowerShellPath -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $LauncherPath 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    [PSCustomObject]@{ ExitCode = $exitCode; Output = ($output | Out-String) }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$installer = Join-Path $repoRoot 'install.ps1'
$launcher = Join-Path $repoRoot 'run-mcp.ps1'
$repoVenv = Join-Path $repoRoot '.venv'
$powerShellPath = (Get-Process -Id $PID).Path
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("multi-agent-plugin-smoke-" + [Guid]::NewGuid().ToString('N'))
$smokeLocalAppData = Join-Path $testRoot 'local-app-data'
$pluginConfigPath = Join-Path $smokeLocalAppData 'OpenAI\multi-agent-router\plugin-config.json'
$codexMarker = Join-Path $testRoot 'codex-was-invoked.txt'
$shimDirectory = Join-Path $testRoot 'shim'
$capturePath = Join-Path $testRoot 'launcher-env.json'
$previousLocalAppData = $env:LOCALAPPDATA
$previousCodexHome = $env:CODEX_HOME
$previousPath = $env:PATH
$previousCapturePath = $env:PLUGIN_MODE_CAPTURE_PATH
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
    'MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER'
)
$previousManagedValues = @{}
foreach ($name in $managedNames) {
    $previousManagedValues[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $repoVenv 'Scripts\python.exe') -PathType Leaf)) {
        throw 'Plugin-mode smoke requires the repository .venv created by the CI dependency step.'
    }

    New-Item -ItemType Directory -Path $shimDirectory, $smokeLocalAppData | Out-Null
    $shim = "@echo off`r`necho invoked>`"$codexMarker`"`r`nexit /b 91`r`n"
    [IO.File]::WriteAllText((Join-Path $shimDirectory 'codex.cmd'), $shim, [Text.Encoding]::ASCII)
    $env:LOCALAPPDATA = $smokeLocalAppData
    $env:CODEX_HOME = Join-Path $testRoot 'codex-home'
    $env:PATH = $shimDirectory

    & $installer -PluginMode -AllowUnsafeCheckoutParent -SkipDependencyInstall -SkipLmStudioProbe `
        -LmStudioBaseUrl 'http://127.0.0.1:4321' -LmStudioModel 'test/model' -AllowedRoot $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Plugin-mode installation failed.'
    }
    if (Test-Path -LiteralPath $codexMarker) {
        throw 'Plugin mode invoked Codex and could create a duplicate global MCP registration.'
    }
    if (Test-Path -LiteralPath (Join-Path $env:CODEX_HOME 'config.toml')) {
        throw 'Plugin mode wrote a global Codex configuration file.'
    }
    if (-not (Test-Path -LiteralPath $pluginConfigPath -PathType Leaf)) {
        throw 'Plugin mode did not create its machine-local configuration.'
    }

    $pluginConfig = [IO.File]::ReadAllText($pluginConfigPath) | ConvertFrom-Json
    Assert-Equal $pluginConfig.schemaVersion 1 'Plugin config schema'
    Assert-Equal $pluginConfig.pythonPath (Join-Path $repoRoot '.venv\Scripts\python.exe') 'Plugin Python path'
    Assert-Equal $pluginConfig.routerPath (Join-Path $repoRoot 'multi_agent_mcp.py') 'Plugin router path'
    Assert-Equal $pluginConfig.environment.MULTI_AGENT_LM_STUDIO_BASE_URL 'http://127.0.0.1:4321/v1' 'Plugin URL'
    Assert-Equal $pluginConfig.environment.MULTI_AGENT_LM_STUDIO_MODEL 'test/model' 'Plugin model'
    Assert-Equal $pluginConfig.environment.MULTI_AGENT_ALLOWED_ROOTS_JSON (ConvertTo-Json -InputObject @($repoRoot) -Compress) 'Plugin allowed roots'
    if ($pluginConfig.environment.PSObject.Properties['LM_API_TOKEN'] -or
        $pluginConfig.environment.PSObject.Properties['MULTI_AGENT_LM_STUDIO_API_KEY']) {
        throw 'Plugin configuration persisted an LM Studio secret.'
    }
    $configAcl = Get-Acl -LiteralPath $pluginConfigPath
    if (-not $configAcl.AreAccessRulesProtected) {
        throw 'Machine-local plugin configuration retained inherited ACLs.'
    }

    & $installer -PluginMode -AllowUnsafeCheckoutParent -SkipDependencyInstall -SkipLmStudioProbe
    $preservedConfig = [IO.File]::ReadAllText($pluginConfigPath) | ConvertFrom-Json
    Assert-Equal $preservedConfig.environment.MULTI_AGENT_LM_STUDIO_BASE_URL 'http://127.0.0.1:4321/v1' 'Preserved plugin URL'
    Assert-Equal $preservedConfig.environment.MULTI_AGENT_LM_STUDIO_MODEL 'test/model' 'Preserved plugin model'

    $cachedLauncherRoot = Join-Path $testRoot 'plugin-cache'
    New-Item -ItemType Directory -Path $cachedLauncherRoot | Out-Null
    Copy-Item -LiteralPath $launcher -Destination $cachedLauncherRoot
    $cachedLauncher = Join-Path $cachedLauncherRoot 'run-mcp.ps1'

    $missingRoot = Join-Path $testRoot 'missing-runtime'
    New-Item -ItemType Directory -Path $missingRoot | Out-Null
    $missingConfig = [ordered]@{
        schemaVersion = 1
        pythonPath = Join-Path $missingRoot '.venv\Scripts\python.exe'
        routerPath = Join-Path $missingRoot 'multi_agent_mcp.py'
        environment = $preservedConfig.environment
    }
    [IO.File]::WriteAllText($pluginConfigPath, (($missingConfig | ConvertTo-Json -Depth 5) + "`n"), (New-Object Text.UTF8Encoding($false)))
    $missingResult = Invoke-Launcher -PowerShellPath $powerShellPath -LauncherPath $cachedLauncher
    Assert-Equal $missingResult.ExitCode 2 'Missing-runtime launcher exit code'
    if ($missingResult.Output -notmatch 'configured private Python environment is missing') {
        throw 'Launcher did not explain the fail-closed missing-runtime result.'
    }

    $launchRoot = Join-Path $testRoot 'launch-runtime'
    New-Item -ItemType Directory -Path $launchRoot | Out-Null
    New-Item -ItemType Junction -Path (Join-Path $launchRoot '.venv') -Target $repoVenv | Out-Null
    $probeScript = @'
import json
import os
from pathlib import Path

names = [
    "MULTI_AGENT_LM_STUDIO_BASE_URL",
    "MULTI_AGENT_LM_STUDIO_MODEL",
    "MULTI_AGENT_ALLOWED_ROOTS_JSON",
]
Path(os.environ["PLUGIN_MODE_CAPTURE_PATH"]).write_text(
    json.dumps({name: os.environ.get(name) for name in names}), encoding="utf-8"
)
'@
    [IO.File]::WriteAllText((Join-Path $launchRoot 'multi_agent_mcp.py'), $probeScript, (New-Object Text.UTF8Encoding($false)))
    $launchConfig = [ordered]@{
        schemaVersion = 1
        pythonPath = Join-Path $launchRoot '.venv\Scripts\python.exe'
        routerPath = Join-Path $launchRoot 'multi_agent_mcp.py'
        environment = $preservedConfig.environment
    }
    [IO.File]::WriteAllText($pluginConfigPath, (($launchConfig | ConvertTo-Json -Depth 5) + "`n"), (New-Object Text.UTF8Encoding($false)))
    foreach ($name in $managedNames) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $env:PLUGIN_MODE_CAPTURE_PATH = $capturePath
    $env:MULTI_AGENT_LM_STUDIO_MODEL = 'env/override'
    $launchResult = Invoke-Launcher -PowerShellPath $powerShellPath -LauncherPath $cachedLauncher
    Assert-Equal $launchResult.ExitCode 0 'Launcher exit code'
    $captured = [IO.File]::ReadAllText($capturePath) | ConvertFrom-Json
    Assert-Equal $captured.MULTI_AGENT_LM_STUDIO_BASE_URL 'http://127.0.0.1:4321/v1' 'Launcher config URL'
    Assert-Equal $captured.MULTI_AGENT_LM_STUDIO_MODEL 'env/override' 'Launcher process-environment precedence'
    Assert-Equal $captured.MULTI_AGENT_ALLOWED_ROOTS_JSON (ConvertTo-Json -InputObject @($repoRoot) -Compress) 'Launcher allowed roots'

    $validConfigText = [IO.File]::ReadAllText($pluginConfigPath)
    [IO.File]::WriteAllText($pluginConfigPath, '{invalid-json', (New-Object Text.UTF8Encoding($false)))
    Remove-Item -LiteralPath $capturePath -Force
    $invalidResult = Invoke-Launcher -PowerShellPath $powerShellPath -LauncherPath $cachedLauncher
    Assert-Equal $invalidResult.ExitCode 2 'Invalid-config launcher exit code'
    if (Test-Path -LiteralPath $capturePath) {
        throw 'Launcher started the router after rejecting invalid configuration.'
    }
    [IO.File]::WriteAllText($pluginConfigPath, $validConfigText, (New-Object Text.UTF8Encoding($false)))

    Write-Host 'PLUGIN_MODE_SMOKE=PASS'
}
finally {
    foreach ($name in $managedNames) {
        [Environment]::SetEnvironmentVariable($name, $previousManagedValues[$name], 'Process')
    }
    $env:LOCALAPPDATA = $previousLocalAppData
    $env:CODEX_HOME = $previousCodexHome
    $env:PATH = $previousPath
    $env:PLUGIN_MODE_CAPTURE_PATH = $previousCapturePath
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTestRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedTestRoot)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

$global:LASTEXITCODE = 0
