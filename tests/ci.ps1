[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-LastExitCode {
    param([Parameter(Mandatory = $true)][string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $repoRoot

& $python -m ruff format --check multi_agent_mcp.py tests
Assert-LastExitCode 'Ruff format check'
& $python -m ruff check .
Assert-LastExitCode 'Ruff lint'
& $python -m unittest discover -s tests -v
Assert-LastExitCode 'Python tests'
& $python -m compileall -q multi_agent_mcp.py tests
Assert-LastExitCode 'Python compileall'
& $python -m pip check
Assert-LastExitCode 'Python dependency check'

$scripts = @(
    'install.ps1',
    'run-mcp.ps1',
    'uninstall.ps1',
    'tests\ci.ps1',
    'tests\install_smoke.ps1',
    'tests\luna_v2_smoke.ps1',
    'tests\plugin_mode_smoke.ps1',
    'skills\integrated-agent-flow\scripts\Enable-LunaV2.ps1'
)
$allErrors = @()
foreach ($script in $scripts) {
    $tokens = $null
    $parseErrors = $null
    [Management.Automation.Language.Parser]::ParseFile(
        (Resolve-Path $script),
        [ref]$tokens,
        [ref]$parseErrors
    ) | Out-Null
    if ($parseErrors) {
        $allErrors += $parseErrors
    }
}
if ($allErrors.Count -gt 0) {
    throw ($allErrors -join "`n")
}

& .\tests\install_smoke.ps1
Assert-LastExitCode 'Standalone installer smoke'
& .\tests\plugin_mode_smoke.ps1
Assert-LastExitCode 'Plugin-mode smoke'
& .\tests\luna_v2_smoke.ps1
Assert-LastExitCode 'Luna v2 compatibility smoke'

Write-Host 'CI_VALIDATION=PASS'
