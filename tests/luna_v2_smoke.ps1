[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-TextEqual {
    param(
        [AllowEmptyString()][string]$Actual,
        [AllowEmptyString()][string]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($Actual -cne $Expected) {
        throw "$Label mismatch."
    }
}

function Write-Utf8Text {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [AllowEmptyString()][string]$Content
    )

    [IO.File]::WriteAllText($Path, $Content, (New-Object Text.UTF8Encoding($false)))
}

function Write-TestCatalog {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ValidateSet('v1', 'v2')][string]$LunaVersion
    )

    $catalog = [ordered]@{
        fetched_at = '2026-08-09T00:00:00Z'
        etag = 'test'
        client_version = '0.147.0'
        models = @(
            [ordered]@{
                slug = 'gpt-5.6-luna'
                display_name = 'GPT-5.6 Luna'
                multi_agent_version = $LunaVersion
            }
        )
    }
    $text = ($catalog | ConvertTo-Json -Depth 8) + "`n"
    Write-Utf8Text -Path $Path -Content $text
    return $text
}

function New-TestHome {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $path = Join-Path $Root $Name
    [void][IO.Directory]::CreateDirectory($path)
    return $path
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$lunaScript = Join-Path $repoRoot 'skills\integrated-agent-flow\scripts\Enable-LunaV2.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) (
    'integrated-agent-luna-v2-' + [Guid]::NewGuid().ToString('N')
)
$fakeCodexScript = Join-Path $testRoot 'fake-codex.ps1'
$fakeCodexCommand = Join-Path $testRoot 'fake-codex.cmd'
$previousCodexHome = $env:CODEX_HOME
$previousFakePowerShell = $env:FAKE_POWERSHELL_EXE
$previousFailDoctor = $env:FAKE_CODEX_FAIL_DOCTOR

try {
    [void][IO.Directory]::CreateDirectory($testRoot)
    $env:FAKE_POWERSHELL_EXE = (Get-Process -Id $PID).Path

    $fakeScriptText = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$commandText = (@($args) -join ' ')

if ($commandText -eq '--version') {
    [Console]::Out.WriteLine('codex-cli 0.147.0')
    exit 0
}

if ($commandText -eq '--strict-config doctor --json') {
    if ($env:FAKE_CODEX_FAIL_DOCTOR -eq '1') {
        exit 9
    }
    $configPath = Join-Path $env:CODEX_HOME 'config.toml'
    $configText = [IO.File]::ReadAllText($configPath)
    $catalogSetting = [Regex]::Match(
        $configText,
        '(?m)^model_catalog_json\s*=\s*"[^"\r\n]+"\s*$'
    )
    if (-not $catalogSetting.Success) {
        [Console]::Error.WriteLine('model_catalog_json was not a standalone top-level key')
        exit 8
    }
    [Console]::Out.WriteLine('{"checks":{"config.load":{"status":"ok"}}}')
    exit 0
}

if ($commandText -eq 'debug models') {
    $catalogPath = Join-Path $env:CODEX_HOME 'models-luna-v2.json'
    if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) {
        [Console]::Error.WriteLine('effective catalog is missing')
        exit 7
    }
    [Console]::Out.Write([IO.File]::ReadAllText($catalogPath))
    exit 0
}

[Console]::Error.WriteLine("unexpected fake Codex arguments: $commandText")
exit 6
'@
    $fakeCommandText = @'
@echo off
"%FAKE_POWERSHELL_EXE%" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0fake-codex.ps1" %*
exit /b %ERRORLEVEL%
'@
    Write-Utf8Text -Path $fakeCodexScript -Content $fakeScriptText
    Write-Utf8Text -Path $fakeCodexCommand -Content ($fakeCommandText -replace "`n", "`r`n")

    # A valid top-level-only config without an EOF newline must gain a separator.
    $noNewlineHome = New-TestHome -Root $testRoot -Name 'no-newline'
    $env:CODEX_HOME = $noNewlineHome
    $env:FAKE_CODEX_FAIL_DOCTOR = $null
    $originalConfig = 'model = "gpt-5.6-sol"'
    Write-Utf8Text -Path (Join-Path $noNewlineHome 'config.toml') -Content $originalConfig
    $originalCatalog = Write-TestCatalog `
        -Path (Join-Path $noNewlineHome 'models_cache.json') -LunaVersion v1

    & $lunaScript -CodexCommand $fakeCodexCommand | Out-Null
    $updatedConfig = [IO.File]::ReadAllText((Join-Path $noNewlineHome 'config.toml'))
    Assert-True `
        -Condition ($updatedConfig -match 'model = "gpt-5\.6-sol"\r?\nmodel_catalog_json\s*=') `
        -Message 'Luna setup concatenated model_catalog_json onto a config without an EOF newline.'
    Assert-TextEqual `
        -Actual ([IO.File]::ReadAllText((Join-Path $noNewlineHome 'models_cache.json'))) `
        -Expected $originalCatalog -Label 'Source model cache'
    $effectiveCatalog = [IO.File]::ReadAllText(
        (Join-Path $noNewlineHome 'models-luna-v2.json')
    ) | ConvertFrom-Json
    Assert-TextEqual `
        -Actual ([string]$effectiveCatalog.models[0].multi_agent_version) `
        -Expected 'v2' -Label 'Effective Luna version'
    $configBackups = @(
        Get-ChildItem -LiteralPath $noNewlineHome -Filter 'config.toml.pre-luna-v2-*.bak'
    )
    Assert-True -Condition ($configBackups.Count -eq 1) -Message 'Config backup was not created.'
    Assert-TextEqual `
        -Actual ([IO.File]::ReadAllText($configBackups[0].FullName)) `
        -Expected $originalConfig -Label 'Config backup'

    # WhatIf must not create the override, a backup, or a config mutation.
    $whatIfHome = New-TestHome -Root $testRoot -Name 'what-if'
    $env:CODEX_HOME = $whatIfHome
    $whatIfConfig = 'model = "gpt-5.6-terra"'
    Write-Utf8Text -Path (Join-Path $whatIfHome 'config.toml') -Content $whatIfConfig
    [void](Write-TestCatalog -Path (Join-Path $whatIfHome 'models_cache.json') -LunaVersion v1)
    & $lunaScript -CodexCommand $fakeCodexCommand -WhatIf | Out-Null
    Assert-TextEqual `
        -Actual ([IO.File]::ReadAllText((Join-Path $whatIfHome 'config.toml'))) `
        -Expected $whatIfConfig -Label 'WhatIf config'
    Assert-True `
        -Condition (-not (Test-Path -LiteralPath (Join-Path $whatIfHome 'models-luna-v2.json'))) `
        -Message 'WhatIf created a Luna override.'
    Assert-True `
        -Condition (@(Get-ChildItem -LiteralPath $whatIfHome -Filter '*.bak').Count -eq 0) `
        -Message 'WhatIf created a backup.'

    # A failed strict-config check must restore both pre-existing files exactly.
    $rollbackHome = New-TestHome -Root $testRoot -Name 'rollback'
    $env:CODEX_HOME = $rollbackHome
    $rollbackConfig = 'model = "gpt-5.6-sol"' + "`n"
    $previousOverride = '{"previous":true}' + "`n"
    Write-Utf8Text -Path (Join-Path $rollbackHome 'config.toml') -Content $rollbackConfig
    Write-Utf8Text -Path (Join-Path $rollbackHome 'models-luna-v2.json') -Content $previousOverride
    $rollbackCatalog = Write-TestCatalog `
        -Path (Join-Path $rollbackHome 'models_cache.json') -LunaVersion v1
    $env:FAKE_CODEX_FAIL_DOCTOR = '1'
    $rollbackFailed = $false
    try {
        & $lunaScript -CodexCommand $fakeCodexCommand | Out-Null
    }
    catch {
        $rollbackFailed = $true
    }
    finally {
        $env:FAKE_CODEX_FAIL_DOCTOR = $null
    }
    Assert-True -Condition $rollbackFailed -Message 'Forced doctor failure did not fail setup.'
    Assert-TextEqual `
        -Actual ([IO.File]::ReadAllText((Join-Path $rollbackHome 'config.toml'))) `
        -Expected $rollbackConfig -Label 'Rolled-back config'
    Assert-TextEqual `
        -Actual ([IO.File]::ReadAllText((Join-Path $rollbackHome 'models-luna-v2.json'))) `
        -Expected $previousOverride -Label 'Rolled-back override'
    Assert-TextEqual `
        -Actual ([IO.File]::ReadAllText((Join-Path $rollbackHome 'models_cache.json'))) `
        -Expected $rollbackCatalog -Label 'Rollback source model cache'

    # An already-v2 source remains v2 and still receives strict validation.
    $alreadyV2Home = New-TestHome -Root $testRoot -Name 'already-v2'
    $env:CODEX_HOME = $alreadyV2Home
    $v2Catalog = Write-TestCatalog `
        -Path (Join-Path $alreadyV2Home 'models_cache.json') -LunaVersion v2
    & $lunaScript -CodexCommand $fakeCodexCommand | Out-Null
    Assert-TextEqual `
        -Actual ([IO.File]::ReadAllText((Join-Path $alreadyV2Home 'models-luna-v2.json'))) `
        -Expected $v2Catalog -Label 'Already-v2 override'

    Write-Host 'LUNA_V2_SMOKE=PASS'
}
finally {
    $env:CODEX_HOME = $previousCodexHome
    $env:FAKE_POWERSHELL_EXE = $previousFakePowerShell
    $env:FAKE_CODEX_FAIL_DOCTOR = $previousFailDoctor
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTestRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedTestRoot)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

$global:LASTEXITCODE = 0
