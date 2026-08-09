[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$ServerName = 'multi_agent',

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-SamePath {
    param([string]$First, [string]$Second)

    if (-not $First -or -not $Second) {
        return $false
    }
    try {
        return (
            [IO.Path]::GetFullPath($First).TrimEnd('\', '/') -ieq
            [IO.Path]::GetFullPath($Second).TrimEnd('\', '/')
        )
    }
    catch {
        return $false
    }
}

$codex = $null
foreach ($candidate in @('codex.cmd', 'codex.exe', 'codex')) {
    $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($resolved) {
        $codex = $resolved.Source
        break
    }
}
if (-not $codex) {
    throw 'Codex CLI was not found.'
}

$listJson = (& $codex mcp list --json | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $listJson.StartsWith('[')) {
    throw 'Could not safely inspect Codex MCP registrations.'
}
try {
    $servers = @($listJson | ConvertFrom-Json)
}
catch {
    throw "Codex returned invalid MCP registration JSON: $($_.Exception.Message)"
}
$registration = $servers | Where-Object { $_.name -eq $ServerName } | Select-Object -First 1
if (-not $registration) {
    Write-Host "Codex MCP server '$ServerName' is not registered."
    return
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$expectedPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$expectedRouter = Join-Path $repoRoot 'multi_agent_mcp.py'
$args = @($registration.transport.args)
$pointsHere =
    (Test-SamePath $registration.transport.command $expectedPython) -and
    $args.Count -gt 0 -and
    (Test-SamePath $args[0] $expectedRouter)
if (-not $pointsHere -and -not $Force) {
    throw "MCP server '$ServerName' points to another installation. Use -Force only after reviewing it."
}

if (-not $PSCmdlet.ShouldProcess($ServerName, 'Remove the Codex MCP registration')) {
    return
}

& $codex mcp remove $ServerName
if ($LASTEXITCODE -ne 0) {
    throw "Failed to remove Codex MCP server '$ServerName'."
}

Write-Host "Removed Codex MCP server '$ServerName'."
Write-Host 'The checkout and its .venv were left intact.'
