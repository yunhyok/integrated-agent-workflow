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

function Get-PropertyValue {
    param($InputObject, [string]$Name)

    $property = $InputObject.PSObject.Properties[$Name]
    if ($property) {
        return $property.Value
    }
    return $null
}

function Resolve-CodexCommand {
    foreach ($candidate in @('codex.cmd', 'codex.exe', 'codex')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw 'Codex CLI was not found.'
}

function Set-OwnerRightsAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    $item = Get-Item -LiteralPath $Path -Force
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = if ($item -is [IO.DirectoryInfo]) {
        New-Object Security.AccessControl.DirectorySecurity
    }
    else {
        New-Object Security.AccessControl.FileSecurity
    }
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($currentSid)
    $inheritanceFlags = if ($item -is [IO.DirectoryInfo]) {
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    }
    else {
        [Security.AccessControl.InheritanceFlags]::None
    }
    foreach ($sidValue in @('S-1-3-4', 'S-1-5-18', 'S-1-5-32-544')) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            (New-Object Security.Principal.SecurityIdentifier($sidValue)),
            [Security.AccessControl.FileSystemRights]::FullControl,
            $inheritanceFlags,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        [void]$acl.AddAccessRule($rule)
    }
    Microsoft.PowerShell.Security\Set-Acl -LiteralPath $item.FullName -AclObject $acl
}

function Assert-RestrictedAcl {
    param([Parameter(Mandatory = $true)][string[]]$Paths)

    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $ownerEquivalentSids = @($currentSid, 'S-1-3-4')
    $fixedTrustedSids = @('S-1-5-18', 'S-1-5-32-544')
    $allowedSids = @($ownerEquivalentSids + $fixedTrustedSids)
    foreach ($path in $Paths) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "ACL fixture is missing: $path"
        }
        $item = Get-Item -LiteralPath $path -Force
        $acl = Get-Acl -LiteralPath $path
        if (-not $acl.AreAccessRulesProtected) {
            throw "ACL inheritance remains enabled: $path"
        }
        if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $currentSid) {
            throw "ACL owner is not the current user: $path"
        }
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        if ($rules.Count -ne 3) {
            throw "ACL contains an unexpected number of rules: $path"
        }
        $expectedInheritance = if ($item -is [IO.DirectoryInfo]) {
            [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
        }
        else {
            [Security.AccessControl.InheritanceFlags]::None
        }
        foreach ($rule in $rules) {
            if ($rule.IdentityReference.Value -notin $allowedSids -or
                $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
                $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
                $rule.InheritanceFlags -ne $expectedInheritance -or
                $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None -or
                $rule.IsInherited) {
                throw "ACL contains an unexpected rule: $path"
            }
        }
        if (@($rules | Where-Object { $_.IdentityReference.Value -in $ownerEquivalentSids }).Count -ne 1) {
            throw "ACL does not contain exactly one owner-equivalent rule: $path"
        }
        foreach ($fixedTrustedSid in $fixedTrustedSids) {
            if (@($rules | Where-Object { $_.IdentityReference.Value -eq $fixedTrustedSid }).Count -ne 1) {
                throw "ACL does not contain exactly one expected SID '$fixedTrustedSid': $path"
            }
        }
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$installer = Join-Path $repoRoot 'install.ps1'
$uninstaller = Join-Path $repoRoot 'uninstall.ps1'
$realCodex = Resolve-CodexCommand
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("multi-agent-install-smoke-" + [Guid]::NewGuid().ToString('N'))
$sameHome = Join-Path $testRoot 'same-home'
$foreignHome = Join-Path $testRoot 'foreign-home'
$rollbackHome = Join-Path $testRoot 'rollback-home'
$shimDirectory = Join-Path $testRoot 'shim'
$previousCodexHome = $env:CODEX_HOME
$previousPath = $env:PATH
$previousShimFailure = $env:MULTI_AGENT_TEST_SHIM_FAIL
$previousLocalAppData = $env:LOCALAPPDATA
$smokeLocalAppData = Join-Path $testRoot 'local-app-data'
$runtimeDirectory = Join-Path $smokeLocalAppData 'OpenAI\multi-agent-router'
$installerSafetyArgs = @{ AllowUnsafeCheckoutParent = $true }
$junctionTarget = Join-Path $testRoot 'junction-target'
$junctionPath = Join-Path $testRoot 'junction-parent'
$unsafeCheckoutParent = Join-Path $testRoot 'unsafe-parent'
$unsafeCheckout = Join-Path $unsafeCheckoutParent 'checkout'
$broadRuntimeDirectory = Join-Path $testRoot 'documents'
$ownerRightsFixtureDirectory = Join-Path $repoRoot ('.tmp\owner-rights-install-smoke-' + [Guid]::NewGuid().ToString('N'))
$ownerRightsFixtureFile = Join-Path $ownerRightsFixtureDirectory 'fixture.txt'

try {
    New-Item -ItemType Directory -Path $sameHome, $foreignHome, $rollbackHome, $shimDirectory, $unsafeCheckout | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $junctionTarget 'nested') -Force | Out-Null
    New-Item -ItemType Junction -Path $junctionPath -Target $junctionTarget | Out-Null
    Copy-Item -LiteralPath $installer, (Join-Path $repoRoot 'multi_agent_mcp.py'), (Join-Path $repoRoot 'requirements.txt') -Destination $unsafeCheckout
    $unsafeParentAcl = Get-Acl -LiteralPath $unsafeCheckoutParent
    $authenticatedUsers = New-Object Security.Principal.SecurityIdentifier('S-1-5-11')
    $unsafeDeleteRule = New-Object Security.AccessControl.FileSystemAccessRule(
        $authenticatedUsers,
        [Security.AccessControl.FileSystemRights]::Delete,
        [Security.AccessControl.InheritanceFlags]::None,
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    )
    [void]$unsafeParentAcl.AddAccessRule($unsafeDeleteRule)
    Set-Acl -LiteralPath $unsafeCheckoutParent -AclObject $unsafeParentAcl
    New-Item -ItemType Directory -Path $broadRuntimeDirectory | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $runtimeDirectory 'stale') -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $runtimeDirectory 'stale\prompt.txt') | Out-Null
    New-Item -ItemType Directory -Path $ownerRightsFixtureDirectory -Force | Out-Null
    New-Item -ItemType File -Path $ownerRightsFixtureFile | Out-Null
    Set-OwnerRightsAcl $ownerRightsFixtureDirectory
    Set-OwnerRightsAcl $ownerRightsFixtureFile
    $global:multiAgentOwnerRightsSetAclTargets = @(
        [IO.Path]::GetFullPath($ownerRightsFixtureDirectory),
        [IO.Path]::GetFullPath($ownerRightsFixtureFile)
    )
    function Set-Acl {
        param(
            [Parameter(Mandatory = $true)][string]$LiteralPath,
            [Parameter(Mandatory = $true)]$AclObject
        )

        $fullPath = [IO.Path]::GetFullPath($LiteralPath)
        if ($fullPath -in $global:multiAgentOwnerRightsSetAclTargets) {
            throw "Installer attempted to rewrite an accepted OWNER RIGHTS ACL: $fullPath"
        }
        Microsoft.PowerShell.Security\Set-Acl -LiteralPath $LiteralPath -AclObject $AclObject
    }
    $env:LOCALAPPDATA = $smokeLocalAppData
    $env:CODEX_HOME = $sameHome

    $oversizedRouterTimeoutWasRejected = $false
    try {
        & $installer @installerSafetyArgs -WhatIf -RouterTimeoutSec 3601 `
            -McpToolTimeoutSec 3602 -LmStudioBaseUrl 'http://127.0.0.1:9' `
            -LmStudioModel 'offline/not-probed'
    }
    catch {
        $oversizedRouterTimeoutWasRejected = $true
    }
    if (-not $oversizedRouterTimeoutWasRejected) {
        throw 'Installer accepted a router timeout above the runtime maximum.'
    }
    & $installer @installerSafetyArgs -WhatIf -RouterTimeoutSec 3600 `
        -McpToolTimeoutSec 3601 -LmStudioBaseUrl 'http://127.0.0.1:9' `
        -LmStudioModel 'offline/not-probed'

    $unsafeInstaller = Join-Path $unsafeCheckout 'install.ps1'
    $unsafeCheckoutWasRejected = $false
    try {
        & $unsafeInstaller -WhatIf -LmStudioBaseUrl 'http://127.0.0.1:9' -LmStudioModel 'offline/not-probed'
    }
    catch {
        $unsafeCheckoutWasRejected = $true
    }
    if (-not $unsafeCheckoutWasRejected) {
        throw 'Checkout under an ancestor with untrusted delete rights was accepted.'
    }
    & $unsafeInstaller -AllowUnsafeCheckoutParent -WhatIf -LmStudioBaseUrl 'http://127.0.0.1:9' -LmStudioModel 'offline/not-probed'

    & $installer @installerSafetyArgs -SkipDependencyInstall -SkipLmStudioProbe -LmStudioBaseUrl 'http://127.0.0.1:4321' -LmStudioModel 'test/model' -RuntimeDirectory $runtimeDirectory -AllowedRoot $repoRoot -EnableUnconfinedCodexReviewer -EnableUnconfinedCopilotReviewer -EnableUnconfinedAntigravityReviewer
    if ($LASTEXITCODE -ne 0) {
        throw 'Initial isolated installation failed.'
    }
    Assert-RestrictedAcl @(
        $repoRoot,
        $installer,
        (Join-Path $repoRoot 'multi_agent_mcp.py'),
        (Join-Path $repoRoot '.venv'),
        (Join-Path $repoRoot '.venv\Scripts\python.exe'),
        $runtimeDirectory,
        (Join-Path $runtimeDirectory 'stale'),
        (Join-Path $runtimeDirectory 'stale\prompt.txt'),
        $ownerRightsFixtureDirectory,
        $ownerRightsFixtureFile
    )

    $sameConfig = Join-Path $sameHome 'config.toml'
    $content = [IO.File]::ReadAllText($sameConfig)
    $newline = if ($content.Contains("`r`n")) { "`r`n" } else { "`n" }
    $content = $content.Replace(
        '[mcp_servers.multi_agent]' + $newline,
        '[mcp_servers.multi_agent]' + $newline + 'enabled_tools = ["ask_codex"]' + $newline
    )
    $content = $content.Replace('startup_timeout_sec = 20.0', 'startup_timeout_sec = 33.0')
    $content = $content.Replace('tool_timeout_sec = 900.0', 'tool_timeout_sec = 777.0')
    $content = $content.Replace(
        'env_vars = ["LM_API_TOKEN", "MULTI_AGENT_LM_STUDIO_API_KEY"]',
        'env_vars = ["LM_API_TOKEN", "MULTI_AGENT_LM_STUDIO_API_KEY", "EXTRA_FORWARDED"]'
    )
    $content = $content.Replace(
        '[mcp_servers.multi_agent.env]' + $newline,
        '[mcp_servers.multi_agent.env]' + $newline + 'CUSTOM_ROUTER_ENV = "preserve-me"' + $newline
    )
    $content += $newline + '[install_smoke]' + $newline + 'preserved = "value"' + $newline
    [IO.File]::WriteAllText($sameConfig, $content, (New-Object Text.UTF8Encoding($false)))

    & $installer @installerSafetyArgs -SkipDependencyInstall -SkipLmStudioProbe
    $registered = (& $realCodex mcp get multi_agent --json | Out-String) | ConvertFrom-Json
    Assert-Equal (Get-PropertyValue $registered.transport.env 'MULTI_AGENT_LM_STUDIO_BASE_URL') 'http://127.0.0.1:4321/v1' 'Preserved URL'
    Assert-Equal (Get-PropertyValue $registered.transport.env 'MULTI_AGENT_LM_STUDIO_MODEL') 'test/model' 'Preserved model'
    Assert-Equal (Get-PropertyValue $registered.transport.env 'MULTI_AGENT_RUNTIME_DIR') $runtimeDirectory 'Runtime directory'
    Assert-Equal (Get-PropertyValue $registered.transport.env 'MULTI_AGENT_ALLOWED_ROOTS_JSON') (ConvertTo-Json -InputObject @($repoRoot) -Compress) 'Allowed roots'
    Assert-Equal (Get-PropertyValue $registered.transport.env 'MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER') '1' 'Unconfined Codex opt-in'
    Assert-Equal (Get-PropertyValue $registered.transport.env 'MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER') '1' 'Unconfined Copilot opt-in'
    Assert-Equal (Get-PropertyValue $registered.transport.env 'MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER') '1' 'Unconfined Antigravity opt-in'
    Assert-Equal (Get-PropertyValue $registered.transport.env 'CUSTOM_ROUTER_ENV') 'preserve-me' 'Custom environment'
    Assert-Equal $registered.startup_timeout_sec 33.0 'Startup timeout'
    Assert-Equal $registered.tool_timeout_sec 777.0 'Tool timeout'
    if ($registered.transport.env_vars -notcontains 'EXTRA_FORWARDED') {
        throw 'Custom forwarded environment variable was not preserved.'
    }
    if ($registered.enabled_tools -notcontains 'ask_codex') {
        throw 'Custom enabled_tools setting was not preserved.'
    }
    $sameText = [IO.File]::ReadAllText($sameConfig)
    if (([Regex]::Matches($sameText, '(?m)^\[mcp_servers\.multi_agent\]$')).Count -ne 1 -or
        $sameText -notmatch '(?m)^preserved = "value"$') {
        throw 'Idempotent installation did not preserve config structure.'
    }

    $beforeWhatIf = (Get-FileHash -LiteralPath $sameConfig -Algorithm SHA256).Hash
    $repoAclBeforeWhatIf = (Get-Acl -LiteralPath $repoRoot).Sddl
    $runtimeAclBeforeWhatIf = (Get-Acl -LiteralPath $runtimeDirectory).Sddl
    & $installer @installerSafetyArgs -WhatIf -LmStudioBaseUrl 'http://127.0.0.1:9' -LmStudioModel 'offline/not-probed'
    $afterWhatIf = (Get-FileHash -LiteralPath $sameConfig -Algorithm SHA256).Hash
    Assert-Equal $afterWhatIf $beforeWhatIf 'WhatIf config hash'
    Assert-Equal (Get-Acl -LiteralPath $repoRoot).Sddl $repoAclBeforeWhatIf 'WhatIf repository ACL'
    Assert-Equal (Get-Acl -LiteralPath $runtimeDirectory).Sddl $runtimeAclBeforeWhatIf 'WhatIf runtime ACL'

    $invalidAllowedRoots = @(
        'C:\',
        '\\server\share',
        (Join-Path $testRoot 'missing-allowed-root'),
        (Join-Path $junctionPath 'nested')
    )
    foreach ($invalidAllowedRoot in $invalidAllowedRoots) {
        $wasRejected = $false
        try {
            & $installer @installerSafetyArgs -WhatIf -AllowedRoot $invalidAllowedRoot -LmStudioBaseUrl 'http://127.0.0.1:9' -LmStudioModel 'offline/not-probed'
        }
        catch {
            $wasRejected = $true
        }
        if (-not $wasRejected) {
            throw "Invalid AllowedRoot was accepted: $invalidAllowedRoot"
        }
        Assert-Equal (Get-Acl -LiteralPath $repoRoot).Sddl $repoAclBeforeWhatIf 'Rejected AllowedRoot repository ACL'
        Assert-Equal (Get-Acl -LiteralPath $runtimeDirectory).Sddl $runtimeAclBeforeWhatIf 'Rejected AllowedRoot runtime ACL'
    }

    $junctionRuntimeWasRejected = $false
    try {
        & $installer @installerSafetyArgs -WhatIf -RuntimeDirectory (Join-Path $junctionPath 'runtime') -LmStudioBaseUrl 'http://127.0.0.1:9' -LmStudioModel 'offline/not-probed'
    }
    catch {
        $junctionRuntimeWasRejected = $true
    }
    if (-not $junctionRuntimeWasRejected) {
        throw 'RuntimeDirectory with a junction parent was accepted.'
    }
    Assert-Equal (Get-Acl -LiteralPath $repoRoot).Sddl $repoAclBeforeWhatIf 'Rejected RuntimeDirectory repository ACL'
    Assert-Equal (Get-Acl -LiteralPath $runtimeDirectory).Sddl $runtimeAclBeforeWhatIf 'Rejected RuntimeDirectory runtime ACL'

    $broadRuntimeAclBeforeWhatIf = (Get-Acl -LiteralPath $broadRuntimeDirectory).Sddl
    $broadRuntimeWasRejected = $false
    try {
        & $installer @installerSafetyArgs -WhatIf -RuntimeDirectory $broadRuntimeDirectory -LmStudioBaseUrl 'http://127.0.0.1:9' -LmStudioModel 'offline/not-probed'
    }
    catch {
        $broadRuntimeWasRejected = $true
    }
    if (-not $broadRuntimeWasRejected) {
        throw 'A broad RuntimeDirectory outside the dedicated OpenAI\multi-agent-router shape was accepted.'
    }
    Assert-Equal (Get-Acl -LiteralPath $repoRoot).Sddl $repoAclBeforeWhatIf 'Broad RuntimeDirectory repository ACL'
    Assert-Equal (Get-Acl -LiteralPath $runtimeDirectory).Sddl $runtimeAclBeforeWhatIf 'Broad RuntimeDirectory active ACL'
    Assert-Equal (Get-Acl -LiteralPath $broadRuntimeDirectory).Sddl $broadRuntimeAclBeforeWhatIf 'Broad RuntimeDirectory candidate ACL'

    $whatIfLocalAppData = Join-Path $testRoot 'whatif-local-app-data'
    $env:LOCALAPPDATA = $whatIfLocalAppData
    & $installer @installerSafetyArgs -WhatIf -LmStudioBaseUrl 'http://127.0.0.1:9' -LmStudioModel 'offline/not-probed'
    if (Test-Path -LiteralPath $whatIfLocalAppData) {
        throw 'WhatIf created a runtime directory.'
    }
    $env:LOCALAPPDATA = $smokeLocalAppData

    $env:CODEX_HOME = $foreignHome
    & $realCodex mcp add multi_agent --env 'MULTI_AGENT_LM_STUDIO_BASE_URL=https://foreign.invalid/v1' --env 'FOREIGN_ONLY=do-not-inherit' -- 'C:\foreign\python.exe' 'C:\foreign\router.py'
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create the foreign-registration fixture.'
    }
    $foreignConfig = Join-Path $foreignHome 'config.toml'
    $foreignHash = (Get-FileHash -LiteralPath $foreignConfig -Algorithm SHA256).Hash
    $foreignWasRejected = $false
    try {
        & $installer @installerSafetyArgs -SkipDependencyInstall -SkipLmStudioProbe -LmStudioBaseUrl 'http://127.0.0.1:4321' -LmStudioModel 'explicit/model'
    }
    catch {
        $foreignWasRejected = $true
    }
    if (-not $foreignWasRejected) {
        throw 'Foreign registration was accepted without ForceRebind.'
    }
    Assert-Equal (Get-FileHash -LiteralPath $foreignConfig -Algorithm SHA256).Hash $foreignHash 'Rejected foreign config hash'

    & $installer @installerSafetyArgs -ForceRebind -SkipDependencyInstall -SkipLmStudioProbe -LmStudioBaseUrl 'http://127.0.0.1:4321' -LmStudioModel 'explicit/model'
    $rebound = (& $realCodex mcp get multi_agent --json | Out-String) | ConvertFrom-Json
    Assert-Equal (Get-PropertyValue $rebound.transport.env 'MULTI_AGENT_LM_STUDIO_BASE_URL') 'http://127.0.0.1:4321/v1' 'Rebound URL'
    Assert-Equal (Get-PropertyValue $rebound.transport.env 'MULTI_AGENT_LM_STUDIO_MODEL') 'explicit/model' 'Rebound model'
    Assert-Equal (Get-PropertyValue $rebound.transport.env 'MULTI_AGENT_ALLOWED_ROOTS_JSON') '[]' 'Fresh allowed roots'
    if (Get-PropertyValue $rebound.transport.env 'MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER') {
        throw 'ForceRebind inherited the unconfined Codex reviewer opt-in.'
    }
    if (Get-PropertyValue $rebound.transport.env 'MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER') {
        throw 'ForceRebind inherited the unconfined Copilot reviewer opt-in.'
    }
    if (Get-PropertyValue $rebound.transport.env 'MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER') {
        throw 'ForceRebind inherited the unconfined Antigravity reviewer opt-in.'
    }
    if (Get-PropertyValue $rebound.transport.env 'FOREIGN_ONLY') {
        throw 'ForceRebind inherited a foreign environment value.'
    }

    & $uninstaller
    $parsedAfterUninstall = ((& $realCodex mcp list --json | Out-String) | ConvertFrom-Json)
    $afterUninstall = @($parsedAfterUninstall)
    if ($afterUninstall | Where-Object { $null -ne $_ -and (Get-PropertyValue $_ 'name') -eq 'multi_agent' }) {
        throw 'Uninstall left the local MCP registration behind.'
    }

    $shimPath = Join-Path $shimDirectory 'codex.cmd'
    $shimText = @"
@echo off
if /I "%MULTI_AGENT_TEST_SHIM_FAIL%"=="list" if /I "%1 %2"=="mcp list" exit /b 42
if /I "%MULTI_AGENT_TEST_SHIM_FAIL%"=="get" if /I "%1 %2"=="mcp get" exit /b 42
"$realCodex" %*
"@
    [IO.File]::WriteAllText($shimPath, $shimText, [Text.Encoding]::ASCII)
    $env:PATH = $shimDirectory + [IO.Path]::PathSeparator + $previousPath

    $env:CODEX_HOME = $rollbackHome
    $env:MULTI_AGENT_TEST_SHIM_FAIL = 'get'
    $rollbackFailed = $false
    try {
        & $installer @installerSafetyArgs -SkipDependencyInstall -SkipLmStudioProbe -LmStudioBaseUrl 'http://127.0.0.1:4321' -LmStudioModel 'test/model'
    }
    catch {
        $rollbackFailed = $true
    }
    if (-not $rollbackFailed -or (Test-Path -LiteralPath (Join-Path $rollbackHome 'config.toml'))) {
        throw 'Fresh-config rollback did not remove the failed registration.'
    }

    $env:MULTI_AGENT_TEST_SHIM_FAIL = 'list'
    $listFailed = $false
    try {
        & $installer @installerSafetyArgs -SkipDependencyInstall -SkipLmStudioProbe
    }
    catch {
        $listFailed = $true
    }
    if (-not $listFailed -or (Test-Path -LiteralPath (Join-Path $rollbackHome 'config.toml'))) {
        throw 'MCP list failure was not fail-closed.'
    }

    Write-Host 'INSTALL_SMOKE=PASS'
}
finally {
    $env:PATH = $previousPath
    $env:CODEX_HOME = $previousCodexHome
    $env:MULTI_AGENT_TEST_SHIM_FAIL = $previousShimFailure
    $env:LOCALAPPDATA = $previousLocalAppData
    Remove-Variable -Name multiAgentOwnerRightsSetAclTargets -Scope Global -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $ownerRightsFixtureDirectory) {
        Remove-Item -LiteralPath $ownerRightsFixtureDirectory -Recurse -Force
    }
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTestRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedTestRoot)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

$global:LASTEXITCODE = 0
