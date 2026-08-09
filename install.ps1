[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$ServerName = 'multi_agent',

    [string]$PythonCommand = '',
    [string]$LmStudioBaseUrl = '',
    [string]$LmStudioModel = '',
    [string]$RuntimeDirectory = '',
    [string[]]$AllowedRoot = @(),

    [ValidateRange(1, 3600)]
    [int]$RouterTimeoutSec = 300,

    [ValidateRange(1, 1000000)]
    [int]$MaxChars = 20000,

    [ValidateRange(1, 1000000)]
    [int]$LmStudioMaxTokens = 2048,

    [AllowEmptyString()]
    [string]$LmStudioReasoningEffort = 'none',

    [ValidateRange(1, 86400)]
    [int]$McpToolTimeoutSec = 900,

    [ValidateRange(1, 86400)]
    [int]$McpStartupTimeoutSec = 20,

    [switch]$SkipDependencyInstall,
    [switch]$SkipLmStudioProbe,
    [switch]$PluginMode,
    [switch]$ForceRebind,
    [switch]$AllowInsecureRemoteLmStudio,
    [switch]$AllowUnauthenticatedRemoteLmStudio,
    [switch]$EnableUnconfinedCodexReviewer,
    [switch]$EnableUnconfinedCopilotReviewer,
    [switch]$EnableUnconfinedAntigravityReviewer,
    [switch]$AllowUnsafeCheckoutParent
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-LmStudioEndpoint {
    param([Parameter(Mandatory = $true)][string]$Value)

    try {
        $uri = [Uri]$Value
    }
    catch {
        throw "LM Studio base URL is invalid: $Value"
    }

    if (-not $uri.IsAbsoluteUri -or $uri.Scheme -notin @('http', 'https')) {
        throw 'LM Studio base URL must be an absolute HTTP(S) URL.'
    }
    if ($uri.UserInfo -or $uri.Query -or $uri.Fragment) {
        throw 'LM Studio base URL must not contain credentials, a query, or a fragment.'
    }
    $path = $uri.AbsolutePath.TrimEnd('/')
    if ($path -notin @('', '/v1')) {
        throw 'LM Studio base URL path must be empty or /v1.'
    }
    $isLoopback = $uri.Host -eq 'localhost'
    $parsedAddress = $null
    if ([Net.IPAddress]::TryParse($uri.Host, [ref]$parsedAddress)) {
        if ($parsedAddress.Equals([Net.IPAddress]::Any) -or
            $parsedAddress.Equals([Net.IPAddress]::IPv6Any)) {
            throw 'Use a client-reachable hostname or IP address, not a wildcard bind address.'
        }
        $isLoopback = [Net.IPAddress]::IsLoopback($parsedAddress)
    }

    $rootUrl = $uri.GetLeftPart([UriPartial]::Authority).TrimEnd('/')
    [PSCustomObject]@{
        BaseUrl = "$rootUrl/v1"
        RootUrl = $rootUrl
        IsLoopback = $isLoopback
        IsHttps = $uri.Scheme -eq 'https'
    }
}

function Get-LocalLmStudioToken {
    foreach ($name in @('MULTI_AGENT_LM_STUDIO_API_KEY', 'LM_API_TOKEN')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if (-not $value) {
            $value = [Environment]::GetEnvironmentVariable($name, 'User')
        }
        if ($value) {
            return $value
        }
    }
    return ''
}

function Protect-SecretText {
    param([string]$Text, [string]$Secret)

    if ($Secret) {
        return $Text.Replace($Secret, '[redacted]')
    }
    return $Text
}

function Resolve-PythonLauncher {
    param([string]$RequestedCommand)

    if ($RequestedCommand) {
        $command = Get-Command $RequestedCommand -ErrorAction Stop
        return [PSCustomObject]@{ Path = $command.Source; PrefixArgs = @() }
    }

    $py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($py) {
        return [PSCustomObject]@{ Path = $py.Source; PrefixArgs = @('-3') }
    }
    foreach ($candidate in @('python.exe', 'python')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return [PSCustomObject]@{ Path = $command.Source; PrefixArgs = @() }
        }
    }
    throw 'Python 3 was not found. Install Python 3.11 or newer and rerun this script.'
}

function Assert-Python311 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string[]]$PrefixArgs = @()
    )

    $version = (& $Path @PrefixArgs -c "import sys; print('.'.join(map(str, sys.version_info[:3]))); raise SystemExit(0 if sys.version_info >= (3, 11) else 3)" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 or newer is required. '$Path' reported version '$version'."
    }
    return $version
}

function Resolve-CodexCommand {
    foreach ($candidate in @('codex.cmd', 'codex.exe', 'codex')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw 'Codex CLI was not found. Install and sign in to Codex before running this script.'
}

function Get-CodexConfigPath {
    if ($env:CODEX_HOME) {
        return Join-Path $env:CODEX_HOME 'config.toml'
    }
    return Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\config.toml'
}

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

function Get-PropertyValue {
    param($InputObject, [string]$Name)

    if ($null -eq $InputObject) {
        return $null
    }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($property) {
        return $property.Value
    }
    return $null
}

function ConvertTo-TomlString {
    param([AllowEmptyString()][string]$Value)

    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    $escaped = $escaped.Replace("`r", '\r').Replace("`n", '\n').Replace("`t", '\t')
    return '"' + $escaped + '"'
}

function ConvertTo-TomlStringArray {
    param([string[]]$Values)

    return '[' + (($Values | ForEach-Object { ConvertTo-TomlString $_ }) -join ', ') + ']'
}

function Set-TomlTableKey {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [Parameter(Mandatory = $true)][string]$TableName,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$TomlValue
    )

    $newline = if ($Content.Contains("`r`n")) { "`r`n" } else { "`n" }
    $headerPattern = "(?m)^[ \t]*\[" + [Regex]::Escape($TableName) + "\][ \t]*(?:#.*)?$"
    $header = [Regex]::Match($Content, $headerPattern)
    if (-not $header.Success) {
        $prefix = $Content.TrimEnd("`r", "`n")
        if ($prefix) {
            $prefix += $newline + $newline
        }
        return $prefix + "[$TableName]" + $newline + "$Key = $TomlValue" + $newline
    }

    $nextHeader = (New-Object Regex('(?m)^[ \t]*\[')).Match($Content, $header.Index + $header.Length)
    $tableEnd = if ($nextHeader.Success) { $nextHeader.Index } else { $Content.Length }
    $tableBodyStart = $header.Index + $header.Length
    $tableBody = $Content.Substring($tableBodyStart, $tableEnd - $tableBodyStart)
    $keyPattern = "(?m)^[ \t]*" + [Regex]::Escape($Key) + "[ \t]*=.*$"
    $keyMatch = [Regex]::Match($tableBody, $keyPattern)
    $replacement = "$Key = $TomlValue"
    if ($keyMatch.Success) {
        $absoluteIndex = $tableBodyStart + $keyMatch.Index
        return $Content.Substring(0, $absoluteIndex) + $replacement + $Content.Substring($absoluteIndex + $keyMatch.Length)
    }

    return $Content.Insert($tableBodyStart, $newline + $replacement)
}

function Remove-TomlTableKey {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [Parameter(Mandatory = $true)][string]$TableName,
        [Parameter(Mandatory = $true)][string]$Key
    )

    $headerPattern = "(?m)^[ \t]*\[" + [Regex]::Escape($TableName) + "\][ \t]*(?:#.*)?$"
    $header = [Regex]::Match($Content, $headerPattern)
    if (-not $header.Success) {
        return $Content
    }
    $nextHeader = (New-Object Regex('(?m)^[ \t]*\[')).Match($Content, $header.Index + $header.Length)
    $tableEnd = if ($nextHeader.Success) { $nextHeader.Index } else { $Content.Length }
    $tableBodyStart = $header.Index + $header.Length
    $tableBody = $Content.Substring($tableBodyStart, $tableEnd - $tableBodyStart)
    $keyPattern = "(?m)^[ \t]*" + [Regex]::Escape($Key) + "[ \t]*=.*(?:\r?\n)?"
    $keyMatch = [Regex]::Match($tableBody, $keyPattern)
    if (-not $keyMatch.Success) {
        return $Content
    }
    $absoluteIndex = $tableBodyStart + $keyMatch.Index
    return $Content.Remove($absoluteIndex, $keyMatch.Length)
}

function Write-AtomicText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $utf8WithoutBom = New-Object Text.UTF8Encoding($false)
    Write-AtomicBytes -Path $Path -Content ($utf8WithoutBom.GetBytes($Content))
}

function Write-AtomicBytes {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][byte[]]$Content
    )

    $temporaryPath = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllBytes($temporaryPath, $Content)
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Get-RestrictedAclTreeItems {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    if (-not (Test-Path -LiteralPath $RootPath -PathType Container)) {
        throw "ACL protection root is not a directory: $RootPath"
    }

    $resolvedRoot = [IO.Path]::GetFullPath((Get-Item -LiteralPath $RootPath -Force).FullName).TrimEnd('\', '/')
    $rootPrefix = $resolvedRoot + [IO.Path]::DirectorySeparatorChar
    $pending = New-Object 'Collections.Generic.Stack[string]'
    $items = New-Object 'Collections.Generic.List[IO.FileSystemInfo]'
    $pending.Push($resolvedRoot)

    while ($pending.Count -gt 0) {
        $currentPath = $pending.Pop()
        $item = Get-Item -LiteralPath $currentPath -Force
        $resolvedItem = [IO.Path]::GetFullPath($item.FullName)
        if ($resolvedItem -ine $resolvedRoot -and
            -not $resolvedItem.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to change an ACL outside '$resolvedRoot': $resolvedItem"
        }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to traverse or modify the ACL of a reparse point: $resolvedItem"
        }

        [void]$items.Add($item)
        if ($item -is [IO.DirectoryInfo]) {
            foreach ($child in @(Get-ChildItem -LiteralPath $resolvedItem -Force)) {
                if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Refusing to traverse or modify the ACL of a reparse point: $($child.FullName)"
                }
                $pending.Push($child.FullName)
            }
        }
    }

    return $items.ToArray()
}

function New-RestrictedAcl {
    param(
        [Parameter(Mandatory = $true)][Security.Principal.SecurityIdentifier]$OwnerSid,
        [Parameter(Mandatory = $true)][bool]$IsDirectory
    )

    $acl = if ($IsDirectory) {
        New-Object Security.AccessControl.DirectorySecurity
    }
    else {
        New-Object Security.AccessControl.FileSecurity
    }
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($OwnerSid)
    $inheritanceFlags = if ($IsDirectory) {
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    }
    else {
        [Security.AccessControl.InheritanceFlags]::None
    }

    foreach ($sidValue in @($OwnerSid.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        $sid = New-Object Security.Principal.SecurityIdentifier($sidValue)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            $inheritanceFlags,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        [void]$acl.AddAccessRule($rule)
    }

    return $acl
}

function Test-RestrictedAclItem {
    param(
        [Parameter(Mandatory = $true)][IO.FileSystemInfo]$Item,
        [Parameter(Mandatory = $true)][Security.Principal.SecurityIdentifier]$OwnerSid
    )

    $ownerEquivalentSids = @($OwnerSid.Value, 'S-1-3-4')
    $fixedTrustedSids = @('S-1-5-18', 'S-1-5-32-544')
    $allowedSids = @($ownerEquivalentSids + $fixedTrustedSids)
    $acl = Get-Acl -LiteralPath $Item.FullName
    $actualOwner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($actualOwner -ne $OwnerSid.Value -or -not $acl.AreAccessRulesProtected) {
        return $false
    }

    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 3) {
        return $false
    }
    $expectedInheritance = if ($Item -is [IO.DirectoryInfo]) {
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
            return $false
        }
    }
    if (@($rules | Where-Object { $_.IdentityReference.Value -in $ownerEquivalentSids }).Count -ne 1) {
        return $false
    }
    foreach ($fixedTrustedSid in $fixedTrustedSids) {
        if (@($rules | Where-Object { $_.IdentityReference.Value -eq $fixedTrustedSid }).Count -ne 1) {
            return $false
        }
    }
    return $true
}

function Protect-RestrictedAclTree {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $ownerSid) {
        throw 'Could not determine the current Windows user SID for ACL protection.'
    }
    $items = @(Get-RestrictedAclTreeItems $RootPath)
    foreach ($item in $items) {
        if (-not (Test-RestrictedAclItem -Item $item -OwnerSid $ownerSid)) {
            $restrictedAcl = New-RestrictedAcl -OwnerSid $ownerSid -IsDirectory ($item -is [IO.DirectoryInfo])
            try {
                Set-Acl -LiteralPath $item.FullName -AclObject $restrictedAcl
            }
            catch {
                throw "Failed to protect ACL for '$($item.FullName)': $($_.Exception.Message)"
            }
            if (-not (Test-RestrictedAclItem -Item $item -OwnerSid $ownerSid)) {
                throw "ACL verification failed after protecting '$($item.FullName)'."
            }
        }
    }
}

function Assert-SafeCheckoutAncestorAcls {
    param([Parameter(Mandatory = $true)][string]$CheckoutRoot)

    $ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $ownerSid) {
        throw 'Could not determine the current Windows user SID for checkout validation.'
    }
    $allowedSids = @($ownerSid.Value, 'S-1-5-18', 'S-1-5-32-544')
    $dangerousMask =
        [long][Security.AccessControl.FileSystemRights]::Delete -bor
        [long][Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [long][Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [long][Security.AccessControl.FileSystemRights]::TakeOwnership

    $currentPath = Split-Path -Parent ([IO.Path]::GetFullPath($CheckoutRoot).TrimEnd('\', '/'))
    while ($currentPath) {
        $acl = Get-Acl -LiteralPath $currentPath
        $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
        foreach ($rule in $rules) {
            if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
                $rule.IdentityReference.Value -in $allowedSids -or
                ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly)) {
                continue
            }
            $rights = [long]$rule.FileSystemRights
            if (($rights -band $dangerousMask) -ne 0) {
                throw (
                    "Checkout ancestor '$currentPath' grants delete or ACL-control rights " +
                    "to untrusted SID '$($rule.IdentityReference.Value)'. Clone under a " +
                    'user-private directory or use -AllowUnsafeCheckoutParent only for an ephemeral test checkout.'
                )
            }
        }

        $parentPath = Split-Path -Parent $currentPath
        if (-not $parentPath -or $parentPath -eq $currentPath) {
            break
        }
        $currentPath = $parentPath
    }
}

function Resolve-LocalDirectoryPath {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$MustExist
    )

    if (-not $Value -or $Value -notmatch '^[A-Za-z]:[\\/]') {
        throw "$Label must be an absolute local drive path, not a relative or UNC path: $Value"
    }
    try {
        $resolvedPath = [IO.Path]::GetFullPath($Value).TrimEnd('\', '/')
    }
    catch {
        throw "$Label is invalid: $Value"
    }
    $pathRoot = [IO.Path]::GetPathRoot($resolvedPath)
    if (-not $pathRoot -or $resolvedPath -ieq $pathRoot.TrimEnd('\', '/')) {
        throw "$Label must not be a filesystem root: $Value"
    }

    try {
        $drive = New-Object IO.DriveInfo($pathRoot)
    }
    catch {
        throw "$Label does not use an available local filesystem drive: $Value"
    }
    if ($drive.DriveType -eq [IO.DriveType]::Network) {
        throw "$Label must not use a mapped network drive: $Value"
    }

    $componentPath = $pathRoot
    $pathComponents = $resolvedPath.Substring($pathRoot.Length).Split(
        [char[]]@('\', '/'),
        [StringSplitOptions]::RemoveEmptyEntries
    )
    foreach ($pathComponent in $pathComponents) {
        $componentPath = Join-Path $componentPath $pathComponent
        if (-not (Test-Path -LiteralPath $componentPath)) {
            break
        }
        $componentItem = Get-Item -LiteralPath $componentPath -Force
        if (($componentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label must not contain a reparse-point component: $componentPath"
        }
        if ($componentItem -isnot [IO.DirectoryInfo] -and $componentPath -ine $resolvedPath) {
            throw "$Label contains a non-directory component: $componentPath"
        }
    }

    if (Test-Path -LiteralPath $resolvedPath) {
        $item = Get-Item -LiteralPath $resolvedPath -Force
        if ($item -isnot [IO.DirectoryInfo]) {
            throw "$Label is not a directory: $resolvedPath"
        }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label must not be a reparse point: $resolvedPath"
        }
        return [IO.Path]::GetFullPath($item.FullName).TrimEnd('\', '/')
    }
    if ($MustExist) {
        throw "$Label does not exist: $resolvedPath"
    }
    return $resolvedPath
}

function ConvertTo-CanonicalAllowedRootsJson {
    param([string[]]$Values = @())

    $canonicalRoots = @()
    foreach ($value in @($Values)) {
        if (-not $value) {
            throw 'AllowedRoot entries must not be empty.'
        }
        $canonicalRoot = Resolve-LocalDirectoryPath -Value $value -Label 'AllowedRoot' -MustExist
        if ($canonicalRoot -notin $canonicalRoots) {
            $canonicalRoots += $canonicalRoot
        }
    }
    return ConvertTo-Json -InputObject @($canonicalRoots) -Compress
}

function Resolve-RouterRuntimeDirectory {
    param([Parameter(Mandatory = $true)][string]$Value)

    $resolvedPath = Resolve-LocalDirectoryPath -Value $Value -Label 'RuntimeDirectory'
    $leaf = Split-Path -Leaf $resolvedPath
    $parentPath = Split-Path -Parent $resolvedPath
    $parentLeaf = Split-Path -Leaf $parentPath
    if ($leaf -ine 'multi-agent-router' -or $parentLeaf -ine 'OpenAI') {
        throw 'RuntimeDirectory must be a dedicated local path ending in OpenAI\multi-agent-router.'
    }
    return $resolvedPath
}

function Update-McpServerSettings {
    param(
        [Parameter(Mandatory = $true)][string]$ConfigPath,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$StartupTimeoutSec,
        [Parameter(Mandatory = $true)][int]$ToolTimeoutSec,
        [Parameter(Mandatory = $true)][Collections.IDictionary]$EnvironmentValues,
        [string[]]$ForwardedEnvironmentVariables = @()
    )

    $content = [IO.File]::ReadAllText($ConfigPath)
    $serverTable = "mcp_servers.$Name"
    $environmentTable = "$serverTable.env"
    $headerPattern = "(?m)^[ \t]*\[" + [Regex]::Escape($serverTable) + "\][ \t]*(?:#.*)?$"
    if (-not [Regex]::IsMatch($content, $headerPattern)) {
        throw "Codex did not create the expected MCP section for '$Name'."
    }

    $content = Set-TomlTableKey $content $serverTable 'startup_timeout_sec' "$StartupTimeoutSec.0"
    $content = Set-TomlTableKey $content $serverTable 'tool_timeout_sec' "$ToolTimeoutSec.0"
    $content = Set-TomlTableKey $content $serverTable 'env_vars' (ConvertTo-TomlStringArray $ForwardedEnvironmentVariables)

    $managedNames = @(
        'MULTI_AGENT_LM_STUDIO_BASE_URL',
        'MULTI_AGENT_LM_STUDIO_MODEL',
        'MULTI_AGENT_LM_STUDIO_MAX_TOKENS',
        'MULTI_AGENT_LM_STUDIO_REASONING_EFFORT',
        'MULTI_AGENT_MAX_CHARS',
        'MULTI_AGENT_TIMEOUT_SEC',
        'MULTI_AGENT_LM_STUDIO_ALLOW_INSECURE_REMOTE',
        'MULTI_AGENT_LM_STUDIO_ALLOW_UNAUTHENTICATED_REMOTE',
        'MULTI_AGENT_RUNTIME_DIR',
        'MULTI_AGENT_ALLOWED_ROOTS_JSON',
        'MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER',
        'MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER',
        'MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER'
    )
    foreach ($managedName in $managedNames) {
        if ($EnvironmentValues.Contains($managedName)) {
            $content = Set-TomlTableKey $content $environmentTable $managedName (ConvertTo-TomlString ([string]$EnvironmentValues[$managedName]))
        }
        else {
            $content = Remove-TomlTableKey $content $environmentTable $managedName
        }
    }

    Write-AtomicText $ConfigPath $content
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$routerPath = Join-Path $repoRoot 'multi_agent_mcp.py'
$requirementsPath = Join-Path $repoRoot 'requirements.txt'
$venvDirectory = Join-Path $repoRoot '.venv'
$venvPython = Join-Path $venvDirectory 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $routerPath) -or -not (Test-Path -LiteralPath $requirementsPath)) {
    throw 'Run install.ps1 from a complete repository checkout.'
}

if (-not $AllowUnsafeCheckoutParent) {
    Assert-SafeCheckoutAncestorAcls $repoRoot
}

$codex = $null
$configPath = $null
$existingRegistration = $null
$existingPointsHere = $false
$existingEnvironment = $null

if ($PluginMode -and $ForceRebind) {
    throw '-ForceRebind is not used with -PluginMode because plugin mode does not create a global MCP registration.'
}

if (-not $PluginMode) {
    $codex = Resolve-CodexCommand
    $configPath = Get-CodexConfigPath
    $configuredServersJson = (& $codex mcp list --json | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to inspect existing Codex MCP registrations.'
    }
    if (-not $configuredServersJson.StartsWith('[')) {
        throw 'Codex MCP registration output was not the expected JSON array.'
    }
    try {
        $parsedServers = $configuredServersJson | ConvertFrom-Json
        $configuredServers = @($parsedServers)
    }
    catch {
        throw "Codex MCP registration output was invalid JSON: $($_.Exception.Message)"
    }
    foreach ($configuredServer in $configuredServers) {
        if ($null -eq $configuredServer) {
            continue
        }
        if (-not (Get-PropertyValue $configuredServer 'name') -or
            -not (Get-PropertyValue $configuredServer 'transport')) {
            throw 'Codex MCP registration output is missing required fields.'
        }
    }
    $existingRegistration = $configuredServers | Where-Object { $_.name -eq $ServerName } | Select-Object -First 1

    if ($existingRegistration) {
        $existingArgs = @($existingRegistration.transport.args)
        $existingPointsHere =
            (Test-SamePath $existingRegistration.transport.command $venvPython) -and
            $existingArgs.Count -gt 0 -and
            (Test-SamePath $existingArgs[0] $routerPath)
        if (-not $existingPointsHere -and -not $ForceRebind) {
            throw "MCP server '$ServerName' already points to another installation. Use -ForceRebind only after reviewing that registration."
        }

        if ($existingPointsHere) {
            $existingEnvironment = $existingRegistration.transport.env
        }
    }
}
else {
    if (-not $env:LOCALAPPDATA) {
        throw 'LOCALAPPDATA is required for machine-local plugin configuration.'
    }
    $pluginConfigDirectory = Join-Path $env:LOCALAPPDATA 'OpenAI\multi-agent-router'
    $pluginConfigPath = Join-Path $pluginConfigDirectory 'plugin-config.json'
    if (Test-Path -LiteralPath $pluginConfigPath -PathType Leaf) {
        try {
            $pluginConfigDocument = [IO.File]::ReadAllText($pluginConfigPath) | ConvertFrom-Json
        }
        catch {
            throw "The existing plugin configuration is invalid JSON: $($_.Exception.Message)"
        }
        if ($pluginConfigDocument.PSObject.Properties['schemaVersion']) {
            if ([int]$pluginConfigDocument.schemaVersion -ne 1 -or
                -not $pluginConfigDocument.PSObject.Properties['environment']) {
                throw 'The existing plugin configuration has an unsupported schema.'
            }
            $existingEnvironment = $pluginConfigDocument.environment
        }
        else {
            # Migrate the flat v0.6.0 preview format on the next successful install.
            $existingEnvironment = $pluginConfigDocument
        }
        $existingRegistration = [PSCustomObject]@{
            startup_timeout_sec = $null
            tool_timeout_sec = $null
            transport = [PSCustomObject]@{ env_vars = @() }
        }
        $existingPointsHere = $true
    }
}

if ($existingPointsHere) {
    $existingBaseUrl = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_LM_STUDIO_BASE_URL'
    $existingModel = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_LM_STUDIO_MODEL'
    $existingAllowInsecure = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_LM_STUDIO_ALLOW_INSECURE_REMOTE'
    $existingAllowUnauthenticated = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_LM_STUDIO_ALLOW_UNAUTHENTICATED_REMOTE'
    $existingRuntimeDirectory = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_RUNTIME_DIR'
    $existingAllowedRootsJson = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_ALLOWED_ROOTS_JSON'
    $existingUnconfinedCodexReviewer = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER'
    $existingUnconfinedCopilotReviewer = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER'
    $existingUnconfinedAntigravityReviewer = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER'
    if (-not $PSBoundParameters.ContainsKey('LmStudioBaseUrl') -and
        $existingBaseUrl) {
        $LmStudioBaseUrl = $existingBaseUrl
    }
    if (-not $PSBoundParameters.ContainsKey('LmStudioModel') -and
        $existingModel) {
        $LmStudioModel = $existingModel
    }
    if (-not $PSBoundParameters.ContainsKey('AllowInsecureRemoteLmStudio') -and
        $existingAllowInsecure -eq '1') {
        $AllowInsecureRemoteLmStudio = $true
    }
    if (-not $PSBoundParameters.ContainsKey('AllowUnauthenticatedRemoteLmStudio') -and
        $existingAllowUnauthenticated -eq '1') {
        $AllowUnauthenticatedRemoteLmStudio = $true
    }
    if (-not $PSBoundParameters.ContainsKey('RuntimeDirectory') -and $existingRuntimeDirectory) {
        $RuntimeDirectory = [string]$existingRuntimeDirectory
    }
    if (-not $PSBoundParameters.ContainsKey('AllowedRoot') -and $null -ne $existingAllowedRootsJson) {
        $allowedRootsText = ([string]$existingAllowedRootsJson).Trim()
        if (-not $allowedRootsText.StartsWith('[') -or -not $allowedRootsText.EndsWith(']')) {
            throw 'The existing MULTI_AGENT_ALLOWED_ROOTS_JSON value is not a JSON array.'
        }
        try {
            $parsedAllowedRoots = $allowedRootsText | ConvertFrom-Json
        }
        catch {
            throw "The existing MULTI_AGENT_ALLOWED_ROOTS_JSON value is invalid JSON: $($_.Exception.Message)"
        }
        $AllowedRoot = @($parsedAllowedRoots)
        foreach ($parsedAllowedRoot in $AllowedRoot) {
            if ($parsedAllowedRoot -isnot [string]) {
                throw 'The existing MULTI_AGENT_ALLOWED_ROOTS_JSON array must contain only strings.'
            }
        }
    }
    if (-not $PSBoundParameters.ContainsKey('EnableUnconfinedCodexReviewer') -and
        $existingUnconfinedCodexReviewer -eq '1') {
        $EnableUnconfinedCodexReviewer = $true
    }
    if (-not $PSBoundParameters.ContainsKey('EnableUnconfinedCopilotReviewer') -and
        $existingUnconfinedCopilotReviewer -eq '1') {
        $EnableUnconfinedCopilotReviewer = $true
    }
    if (-not $PSBoundParameters.ContainsKey('EnableUnconfinedAntigravityReviewer') -and
        $existingUnconfinedAntigravityReviewer -eq '1') {
        $EnableUnconfinedAntigravityReviewer = $true
    }

    $integerSettings = @(
        @{ Parameter = 'RouterTimeoutSec'; Environment = 'MULTI_AGENT_TIMEOUT_SEC'; Minimum = 1; Maximum = 3600 },
        @{ Parameter = 'MaxChars'; Environment = 'MULTI_AGENT_MAX_CHARS'; Minimum = 1; Maximum = 1000000 },
        @{ Parameter = 'LmStudioMaxTokens'; Environment = 'MULTI_AGENT_LM_STUDIO_MAX_TOKENS'; Minimum = 1; Maximum = 1000000 }
    )
    foreach ($setting in $integerSettings) {
        if (-not $PSBoundParameters.ContainsKey($setting.Parameter)) {
            $rawValue = Get-PropertyValue $existingEnvironment $setting.Environment
            $parsedValue = 0
            if ($rawValue -and [int]::TryParse([string]$rawValue, [ref]$parsedValue) -and
                $parsedValue -ge $setting.Minimum -and $parsedValue -le $setting.Maximum) {
                Set-Variable -Name $setting.Parameter -Value $parsedValue
            }
        }
    }
    if (-not $PSBoundParameters.ContainsKey('LmStudioReasoningEffort')) {
        $existingReasoningEffort = Get-PropertyValue $existingEnvironment 'MULTI_AGENT_LM_STUDIO_REASONING_EFFORT'
        if ($null -ne $existingReasoningEffort) {
            $LmStudioReasoningEffort = [string]$existingReasoningEffort
        }
    }
    if (-not $PSBoundParameters.ContainsKey('McpStartupTimeoutSec') -and
        $null -ne $existingRegistration.startup_timeout_sec) {
        $McpStartupTimeoutSec = [int]$existingRegistration.startup_timeout_sec
    }
    if (-not $PSBoundParameters.ContainsKey('McpToolTimeoutSec') -and
        $null -ne $existingRegistration.tool_timeout_sec) {
        $McpToolTimeoutSec = [int]$existingRegistration.tool_timeout_sec
    }
}

if (-not $LmStudioBaseUrl) {
    $LmStudioBaseUrl = 'http://127.0.0.1:1234'
}

if (-not $RuntimeDirectory) {
    if (-not $env:LOCALAPPDATA) {
        throw 'LOCALAPPDATA is required to select the default router runtime directory.'
    }
    $RuntimeDirectory = Join-Path $env:LOCALAPPDATA 'OpenAI\multi-agent-router'
}
$runtimeDirectory = Resolve-RouterRuntimeDirectory $RuntimeDirectory
$allowedRootsJson = ConvertTo-CanonicalAllowedRootsJson $AllowedRoot

$endpoint = Get-LmStudioEndpoint $LmStudioBaseUrl
$lmStudioToken = Get-LocalLmStudioToken
if (-not $endpoint.IsLoopback) {
    if (-not $endpoint.IsHttps -and -not $AllowInsecureRemoteLmStudio) {
        throw 'Remote LM Studio requires HTTPS. Use -AllowInsecureRemoteLmStudio only on an explicitly trusted network.'
    }
    if (-not $lmStudioToken -and -not $AllowUnauthenticatedRemoteLmStudio) {
        throw 'Remote LM Studio requires LM_API_TOKEN or MULTI_AGENT_LM_STUDIO_API_KEY. Set it as a user environment variable first.'
    }
}

if ($McpToolTimeoutSec -le $RouterTimeoutSec) {
    throw 'McpToolTimeoutSec must be greater than RouterTimeoutSec.'
}

$installAction = if ($PluginMode) {
    'Install dependencies and write machine-local plugin configuration without global MCP registration'
}
else {
    "Install dependencies and register Codex MCP server '$ServerName'"
}
if (-not $PSCmdlet.ShouldProcess($repoRoot, $installAction)) {
    return
}

Protect-RestrictedAclTree $repoRoot
if (-not (Test-Path -LiteralPath $runtimeDirectory)) {
    [void][IO.Directory]::CreateDirectory($runtimeDirectory)
}
if (-not (Test-Path -LiteralPath $runtimeDirectory -PathType Container)) {
    throw "Router runtime path is not a directory: $runtimeDirectory"
}
Protect-RestrictedAclTree $runtimeDirectory

if (-not $SkipLmStudioProbe) {
    $headers = @{}
    if ($lmStudioToken) {
        $headers.Authorization = "Bearer $lmStudioToken"
    }
    try {
        $probe = Invoke-RestMethod -Method Get -Uri "$($endpoint.RootUrl)/api/v1/models" -Headers $headers -TimeoutSec 10 -MaximumRedirection 0
        $models = @(
            @(
                foreach ($nativeModel in @(Get-PropertyValue $probe 'models')) {
                    if ((Get-PropertyValue $nativeModel 'type') -ne 'llm') {
                        continue
                    }
                    $nativeKey = Get-PropertyValue $nativeModel 'key'
                    if ($nativeKey -is [string] -and $nativeKey.Trim()) {
                        $nativeKey.Trim()
                    }
                    foreach ($loadedInstance in @(Get-PropertyValue $nativeModel 'loaded_instances')) {
                        $loadedInstanceId = Get-PropertyValue $loadedInstance 'id'
                        if ($loadedInstanceId -is [string] -and $loadedInstanceId.Trim()) {
                            $loadedInstanceId.Trim()
                        }
                    }
                }
            ) | Select-Object -Unique
        )
        if ($LmStudioModel -and $LmStudioModel -notin $models) {
            $availableModels = if ($models.Count -gt 0) { $models -join ', ' } else { '(none)' }
            throw "Configured model '$LmStudioModel' is not advertised. Available LLMs: $availableModels"
        }
        if (-not $LmStudioModel -and $models.Count -eq 1) {
            $LmStudioModel = $models[0]
            Write-Host "Selected the only advertised LM Studio model: $LmStudioModel"
        }
        elseif (-not $LmStudioModel -and $models.Count -gt 1) {
            Write-Warning "Multiple LM Studio models are advertised. Rerun with -LmStudioModel and one of: $($models -join ', ')"
        }
    }
    catch {
        $detail = Protect-SecretText $_.Exception.Message $lmStudioToken
        throw "LM Studio probe failed: $detail Use -SkipLmStudioProbe only to configure an intentionally offline server."
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $python = Resolve-PythonLauncher $PythonCommand
    $pythonVersion = Assert-Python311 $python.Path $python.PrefixArgs
    Write-Host "Using Python $pythonVersion to create the virtual environment."
    $venvArguments = @($python.PrefixArgs) + @('-m', 'venv', $venvDirectory)
    & $python.Path @venvArguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create the Python virtual environment.'
    }
}

$venvVersion = Assert-Python311 $venvPython
Write-Host "Virtual environment Python: $venvVersion"

if (-not $SkipDependencyInstall) {
    & $venvPython -m pip install --disable-pip-version-check -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install Python dependencies.'
    }
}

& $venvPython -c 'import mcp'
if ($LASTEXITCODE -ne 0) {
    throw 'The virtual environment cannot import the required mcp package.'
}
& $venvPython -m py_compile $routerPath
if ($LASTEXITCODE -ne 0) {
    throw 'The MCP router failed Python compilation.'
}

$environmentValues = [ordered]@{
    MULTI_AGENT_LM_STUDIO_BASE_URL = $endpoint.BaseUrl
    MULTI_AGENT_LM_STUDIO_MAX_TOKENS = [string]$LmStudioMaxTokens
    MULTI_AGENT_LM_STUDIO_REASONING_EFFORT = $LmStudioReasoningEffort
    MULTI_AGENT_MAX_CHARS = [string]$MaxChars
    MULTI_AGENT_TIMEOUT_SEC = [string]$RouterTimeoutSec
    MULTI_AGENT_RUNTIME_DIR = $runtimeDirectory
    MULTI_AGENT_ALLOWED_ROOTS_JSON = $allowedRootsJson
}
if ($LmStudioModel) {
    $environmentValues.MULTI_AGENT_LM_STUDIO_MODEL = $LmStudioModel
}
if ($AllowInsecureRemoteLmStudio) {
    $environmentValues.MULTI_AGENT_LM_STUDIO_ALLOW_INSECURE_REMOTE = '1'
}
if ($AllowUnauthenticatedRemoteLmStudio) {
    $environmentValues.MULTI_AGENT_LM_STUDIO_ALLOW_UNAUTHENTICATED_REMOTE = '1'
}
if ($EnableUnconfinedCodexReviewer) {
    $environmentValues.MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER = '1'
}
if ($EnableUnconfinedCopilotReviewer) {
    $environmentValues.MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER = '1'
}
if ($EnableUnconfinedAntigravityReviewer) {
    $environmentValues.MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER = '1'
}

if ($PluginMode) {
    if (-not (Test-Path -LiteralPath $pluginConfigDirectory)) {
        [void][IO.Directory]::CreateDirectory($pluginConfigDirectory)
    }
    if (-not (Test-Path -LiteralPath $pluginConfigDirectory -PathType Container)) {
        throw "Plugin configuration path is not a directory: $pluginConfigDirectory"
    }
    Protect-RestrictedAclTree $pluginConfigDirectory
    $pluginConfigDocument = [ordered]@{
        schemaVersion = 1
        pythonPath = [IO.Path]::GetFullPath($venvPython)
        routerPath = [IO.Path]::GetFullPath($routerPath)
        environment = $environmentValues
    }
    $pluginConfigText = ($pluginConfigDocument | ConvertTo-Json -Depth 5) + "`n"
    $pluginConfigExisted = Test-Path -LiteralPath $pluginConfigPath -PathType Leaf
    [byte[]]$originalPluginConfigBytes = if ($pluginConfigExisted) {
        [IO.File]::ReadAllBytes($pluginConfigPath)
    }
    else {
        @()
    }
    try {
        Write-AtomicText $pluginConfigPath $pluginConfigText
        Protect-RestrictedAclTree $repoRoot
        Protect-RestrictedAclTree $runtimeDirectory
        Protect-RestrictedAclTree $pluginConfigDirectory
        if ([IO.File]::ReadAllText($pluginConfigPath) -cne $pluginConfigText) {
            throw 'Plugin configuration verification returned unexpected content.'
        }
    }
    catch {
        $installFailure = $_
        try {
            if ($pluginConfigExisted) {
                Write-AtomicBytes -Path $pluginConfigPath -Content $originalPluginConfigBytes
            }
            elseif (Test-Path -LiteralPath $pluginConfigPath) {
                Remove-Item -LiteralPath $pluginConfigPath -Force
            }
        }
        catch {
            throw (
                "Plugin installation failed and the prior machine-local configuration could not be restored. " +
                "Install error: $($installFailure.Exception.Message) Rollback error: $($_.Exception.Message)"
            )
        }
        throw $installFailure
    }

    Write-Host ''
    Write-Host 'Prepared the plugin MCP runtime without creating a global Codex MCP registration.'
    Write-Host "Machine-local plugin configuration: $pluginConfigPath"
    Write-Host "LM Studio URL (this PC only): $($endpoint.BaseUrl)"
    if ($LmStudioModel) {
        Write-Host "LM Studio model (this PC only): $LmStudioModel"
    }
    else {
        Write-Warning 'No default LM Studio model was saved. Pass model=... per call or rerun this installer with -PluginMode -LmStudioModel.'
    }
    Write-Host 'Restart Codex so the plugin MCP server is recreated.'
    return
}

$forwardedEnvironmentVariables = @('LM_API_TOKEN', 'MULTI_AGENT_LM_STUDIO_API_KEY')
if ($existingPointsHere) {
    $forwardedEnvironmentVariables = @(
        @($existingRegistration.transport.env_vars) + $forwardedEnvironmentVariables |
            Where-Object { $_ } |
            Select-Object -Unique
    )
}

$originalConfig = if (Test-Path -LiteralPath $configPath) {
    [IO.File]::ReadAllText($configPath)
}
else {
    $null
}

try {
    if ($existingRegistration -and -not $existingPointsHere) {
        & $codex mcp remove $ServerName
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove the existing '$ServerName' registration."
        }
    }

    if (-not $existingPointsHere) {
        $addArguments = @('mcp', 'add', $ServerName)
        foreach ($entry in $environmentValues.GetEnumerator()) {
            $addArguments += @('--env', "$($entry.Key)=$($entry.Value)")
        }
        $addArguments += @('--', $venvPython, $routerPath)

        & $codex @addArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to register '$ServerName' with Codex."
        }
    }

    Update-McpServerSettings -ConfigPath $configPath -Name $ServerName -StartupTimeoutSec $McpStartupTimeoutSec -ToolTimeoutSec $McpToolTimeoutSec -EnvironmentValues $environmentValues -ForwardedEnvironmentVariables $forwardedEnvironmentVariables
    $registeredJson = (& $codex mcp get $ServerName --json | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $registeredJson) {
        throw "Failed to verify '$ServerName' after registration."
    }
    try {
        $registered = $registeredJson | ConvertFrom-Json
    }
    catch {
        throw "Codex returned invalid registration JSON: $($_.Exception.Message)"
    }
    $registeredArgs = @($registered.transport.args)
    $registeredEnvironment = $registered.transport.env
    if (-not (Test-SamePath $registered.transport.command $venvPython) -or
        $registeredArgs.Count -lt 1 -or
        -not (Test-SamePath $registeredArgs[0] $routerPath)) {
        throw 'Codex registration verification returned an unexpected Python path.'
    }
    foreach ($entry in $environmentValues.GetEnumerator()) {
        if ((Get-PropertyValue $registeredEnvironment $entry.Key) -ne [string]$entry.Value) {
            throw "Codex registration verification returned an unexpected value for '$($entry.Key)'."
        }
    }
    if (-not $environmentValues.Contains('MULTI_AGENT_LM_STUDIO_MODEL') -and
        (Get-PropertyValue $registeredEnvironment 'MULTI_AGENT_LM_STUDIO_MODEL')) {
        throw 'Codex registration verification unexpectedly retained an LM Studio model.'
    }
    if (-not $environmentValues.Contains('MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER') -and
        (Get-PropertyValue $registeredEnvironment 'MULTI_AGENT_ENABLE_UNCONFINED_CODEX_REVIEWER')) {
        throw 'Codex registration verification unexpectedly retained the unconfined Codex reviewer opt-in.'
    }
    if (-not $environmentValues.Contains('MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER') -and
        (Get-PropertyValue $registeredEnvironment 'MULTI_AGENT_ENABLE_UNCONFINED_COPILOT_REVIEWER')) {
        throw 'Codex registration verification unexpectedly retained the unconfined Copilot reviewer opt-in.'
    }
    if (-not $environmentValues.Contains('MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER') -and
        (Get-PropertyValue $registeredEnvironment 'MULTI_AGENT_ENABLE_UNCONFINED_ANTIGRAVITY_REVIEWER')) {
        throw 'Codex registration verification unexpectedly retained the unconfined Antigravity reviewer opt-in.'
    }
    foreach ($forwardedName in $forwardedEnvironmentVariables) {
        if ($registered.transport.env_vars -notcontains $forwardedName) {
            throw "Codex registration is not forwarding expected variable '$forwardedName'."
        }
    }
    if ($registered.startup_timeout_sec -ne [double]$McpStartupTimeoutSec -or
        $registered.tool_timeout_sec -ne [double]$McpToolTimeoutSec) {
        throw 'Codex registration verification returned unexpected MCP timeouts.'
    }
    Protect-RestrictedAclTree $repoRoot
    Protect-RestrictedAclTree $runtimeDirectory
}
catch {
    if ($null -ne $originalConfig) {
        Write-AtomicText $configPath $originalConfig
    }
    elseif (Test-Path -LiteralPath $configPath) {
        Remove-Item -LiteralPath $configPath -Force
    }
    throw
}

Write-Host ''
Write-Host "Registered Codex MCP server '$ServerName'."
Write-Host "LM Studio URL (this PC only): $($endpoint.BaseUrl)"
if ($LmStudioModel) {
    Write-Host "LM Studio model (this PC only): $LmStudioModel"
}
else {
    Write-Warning 'No default LM Studio model was saved. Pass model=... per call or rerun this installer with -LmStudioModel.'
}
Write-Host "Restart Codex, then run: codex mcp get $ServerName --json"
