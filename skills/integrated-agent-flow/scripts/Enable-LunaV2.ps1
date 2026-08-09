[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$CodexCommand = 'codex'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-CodexHomePath {
    if ($env:CODEX_HOME) {
        return [IO.Path]::GetFullPath($env:CODEX_HOME)
    }
    return Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
}

function ConvertTo-TomlString {
    param([Parameter(Mandatory = $true)][string]$Value)

    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    return '"' + $escaped + '"'
}

function Write-AtomicText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $temporaryPath = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    $utf8WithoutBom = New-Object Text.UTF8Encoding($false)
    try {
        [IO.File]::WriteAllText($temporaryPath, $Content, $utf8WithoutBom)
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Set-TopLevelModelCatalog {
    param(
        [AllowEmptyString()][string]$Content,
        [Parameter(Mandatory = $true)][string]$CatalogPath
    )

    $newline = if ($Content.Contains("`r`n")) { "`r`n" } else { "`n" }
    $firstTable = [Regex]::Match($Content, '(?m)^\s*\[')
    $prefixEnd = if ($firstTable.Success) { $firstTable.Index } else { $Content.Length }
    $prefix = $Content.Substring(0, $prefixEnd)
    $keyMatch = [Regex]::Match($prefix, '(?m)^\s*model_catalog_json\s*=.*$')
    $setting = 'model_catalog_json = ' + (ConvertTo-TomlString $CatalogPath)
    if ($keyMatch.Success) {
        return $Content.Substring(0, $keyMatch.Index) + $setting + $Content.Substring($keyMatch.Index + $keyMatch.Length)
    }

    $separator = if ($prefix.Length -gt 0 -and -not $prefix.EndsWith("`n")) {
        $newline
    }
    else {
        ''
    }
    $insertion = $separator + $setting + $newline + $newline
    return $Content.Insert($prefixEnd, $insertion)
}

$codex = (Get-Command $CodexCommand -ErrorAction Stop).Source
$versionText = (& $codex --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'Could not determine the Codex CLI version.'
}
$versionMatch = [Regex]::Match($versionText, '\d+\.\d+\.\d+')
if (-not $versionMatch.Success -or [Version]$versionMatch.Value -lt [Version]'0.147.0') {
    throw "Codex CLI 0.147.0 or newer is required. Found: $versionText"
}

$codexHome = Get-CodexHomePath
$configPath = Join-Path $codexHome 'config.toml'
$cachePath = Join-Path $codexHome 'models_cache.json'
$overridePath = Join-Path $codexHome 'models-luna-v2.json'
if (-not (Test-Path -LiteralPath $cachePath)) {
    throw "Codex model cache was not found: $cachePath"
}

$cacheText = [IO.File]::ReadAllText($cachePath)
try {
    $cacheJson = $cacheText | ConvertFrom-Json
}
catch {
    throw "Codex model cache is invalid JSON: $($_.Exception.Message)"
}
$lunaEntries = @($cacheJson.models | Where-Object { $_.slug -eq 'gpt-5.6-luna' })
if ($lunaEntries.Count -ne 1) {
    throw "Expected exactly one gpt-5.6-luna entry; found $($lunaEntries.Count)."
}
$sourceVersion = [string]$lunaEntries[0].multi_agent_version
if ($sourceVersion -notin @('v1', 'v2')) {
    throw "Unsupported Luna multi_agent_version in cache: '$sourceVersion'."
}

$overrideText = $cacheText
if ($sourceVersion -eq 'v1') {
    $pattern = '(?s)("slug"\s*:\s*"gpt-5\.6-luna".*?"multi_agent_version"\s*:\s*")v1(")'
    $regex = New-Object Regex($pattern)
    if ($regex.Matches($cacheText).Count -ne 1) {
        throw 'Could not isolate the Luna multi_agent_version field safely.'
    }
    $overrideText = $regex.Replace($cacheText, '${1}v2${2}', 1)
}

$overrideJson = $overrideText | ConvertFrom-Json
$effectiveLuna = @($overrideJson.models | Where-Object { $_.slug -eq 'gpt-5.6-luna' })
if ($effectiveLuna.Count -ne 1 -or $effectiveLuna[0].multi_agent_version -ne 'v2') {
    throw 'Generated catalog did not contain exactly one Luna v2 entry.'
}

$configExisted = Test-Path -LiteralPath $configPath
$overrideExisted = Test-Path -LiteralPath $overridePath
$configText = if ($configExisted) { [IO.File]::ReadAllText($configPath) } else { '' }
$previousOverride = if ($overrideExisted) { [IO.File]::ReadAllText($overridePath) } else { $null }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$configBackup = if ($configExisted) { "$configPath.pre-luna-v2-$stamp.bak" } else { $null }
$overrideBackup = if ($overrideExisted) { "$overridePath.pre-refresh-$stamp.bak" } else { $null }

if (-not $PSCmdlet.ShouldProcess($codexHome, 'Enable the explicit GPT-5.6 Luna v2 model catalog override')) {
    return
}

try {
    if ($configBackup) {
        Copy-Item -LiteralPath $configPath -Destination $configBackup
    }
    if ($overrideBackup) {
        Copy-Item -LiteralPath $overridePath -Destination $overrideBackup
    }

    Write-AtomicText $overridePath $overrideText
    $updatedConfig = Set-TopLevelModelCatalog $configText $overridePath
    Write-AtomicText $configPath $updatedConfig

    $doctorJson = (& $codex --strict-config doctor --json | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $doctorJson) {
        throw 'Codex strict configuration validation failed.'
    }
    $doctor = $doctorJson | ConvertFrom-Json
    $configLoad = $doctor.checks.PSObject.Properties['config.load']
    if (-not $configLoad -or $configLoad.Value.status -ne 'ok') {
        throw 'Codex doctor did not report a valid strict configuration load.'
    }

    $modelsJson = (& $codex debug models | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $modelsJson) {
        throw 'Could not read the effective Codex model catalog.'
    }
    $models = $modelsJson | ConvertFrom-Json
    $effective = @($models.models | Where-Object { $_.slug -eq 'gpt-5.6-luna' })
    if ($effective.Count -ne 1 -or $effective[0].multi_agent_version -ne 'v2') {
        throw 'The effective Codex model catalog does not advertise Luna as v2.'
    }
}
catch {
    if ($configExisted) {
        Write-AtomicText $configPath $configText
    }
    elseif (Test-Path -LiteralPath $configPath) {
        Remove-Item -LiteralPath $configPath -Force
    }
    if ($overrideExisted) {
        Write-AtomicText $overridePath $previousOverride
    }
    elseif (Test-Path -LiteralPath $overridePath) {
        Remove-Item -LiteralPath $overridePath -Force
    }
    throw
}

$sourceHash = (Get-FileHash -LiteralPath $cachePath -Algorithm SHA256).Hash
$overrideHash = (Get-FileHash -LiteralPath $overridePath -Algorithm SHA256).Hash
Write-Host "Codex CLI: $versionText"
Write-Host "Source catalog SHA-256: $sourceHash"
Write-Host "Override catalog SHA-256: $overrideHash"
Write-Host 'Effective gpt-5.6-luna multi_agent_version: v2'
if ($configBackup) {
    Write-Host "Config backup: $configBackup"
}
if ($overrideBackup) {
    Write-Host "Previous override backup: $overrideBackup"
}
Write-Host 'Fully restart Codex before spawning a GPT-5.6 Luna child.'
