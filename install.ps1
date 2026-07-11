# Devbox installer for Windows PowerShell 5.1 and PowerShell.
$ErrorActionPreference = 'Stop'
$DevboxRef = if ($env:DEVBOX_REF) { $env:DEVBOX_REF } else { 'main' }
$DevboxSourceUrl = if ($env:DEVBOX_SOURCE_URL) { $env:DEVBOX_SOURCE_URL } else { "https://raw.githubusercontent.com/alexandru/devbox/$DevboxRef/bin/devbox" }
$DevboxWingetPackage = 'Python.Python.3.13'

function Write-InstallerMessage([string] $Message) { Write-Host "devbox installer: $Message" }
function Throw-InstallerError([string] $Message) { throw "devbox installer: error: $Message" }

function Test-PythonVersion {
    param([string] $PythonCommand)
    try {
        & $PythonCommand -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-CompatiblePython {
    $candidates = @(@('py', '-3'), @('python3'), @('python'))
    foreach ($candidate in $candidates) {
        $command = $candidate[0]
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { continue }
        try {
            if ($candidate.Count -eq 2) {
                & $command $candidate[1] -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ Command = $command; Arguments = @($candidate[1]); Executable = (& $command $candidate[1] -c 'import sys; print(sys.executable)').Trim() } }
            } elseif (Test-PythonVersion $command) {
                return @{ Command = $command; Arguments = @(); Executable = (& $command -c 'import sys; print(sys.executable)').Trim() }
            }
        } catch { }
    }
    return $null
}

function Get-PythonInstallPlan {
    if (Get-Command winget -ErrorAction SilentlyContinue) { return 'winget' }
    if (Get-Command choco -ErrorAction SilentlyContinue) { return 'choco' }
    if (Get-Command scoop -ErrorAction SilentlyContinue) { return 'scoop' }
    return $null
}

function Install-PythonWithWinget { & winget install --id $DevboxWingetPackage --exact --scope user --source winget --accept-package-agreements --accept-source-agreements; if ($LASTEXITCODE -ne 0) { Throw-InstallerError 'winget failed to install Python.' } }
function Install-PythonWithChocolatey {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { Throw-InstallerError 'Chocolatey requires an elevated PowerShell session.' }
    & choco install python3 -y; if ($LASTEXITCODE -ne 0) { Throw-InstallerError 'Chocolatey failed to install Python.' }
}
function Install-PythonWithScoop { & scoop install python; if ($LASTEXITCODE -ne 0) { Throw-InstallerError 'Scoop failed to install Python.' } }

function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machine, $user, $env:Path) | Where-Object { $_ }) -join ';'
}

function Get-DevboxSource([string] $Destination) {
    if ($env:DEVBOX_SOURCE_FILE) {
        if (-not (Test-Path -LiteralPath $env:DEVBOX_SOURCE_FILE -PathType Leaf)) { Throw-InstallerError "DEVBOX_SOURCE_FILE does not exist: $($env:DEVBOX_SOURCE_FILE)" }
        Copy-Item -LiteralPath $env:DEVBOX_SOURCE_FILE -Destination $Destination -Force
    } else {
        Invoke-WebRequest -Uri $DevboxSourceUrl -OutFile $Destination -UseBasicParsing
    }
}

function Add-PathEntry {
    param([string] $PathValue, [string] $ExistingPath)
    $normal = $PathValue.TrimEnd('\').ToLowerInvariant()
    $entries = @($ExistingPath -split ';' | Where-Object { $_ })
    foreach ($entry in $entries) { if ($entry.TrimEnd('\').ToLowerInvariant() -eq $normal) { return $ExistingPath } }
    return (($entries + $PathValue) -join ';')
}

function Add-UserPathEntry([string] $InstallDirectory) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $updated = Add-PathEntry -PathValue $InstallDirectory -ExistingPath $current
    if ($updated -ne $current) { [Environment]::SetEnvironmentVariable('Path', $updated, 'User') }
    $env:Path = Add-PathEntry -PathValue $InstallDirectory -ExistingPath $env:Path
}

function Install-DevboxLauncher {
    param($Python, [string] $InstallDirectory)
    New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null
    $scriptPath = Join-Path $InstallDirectory 'devbox.py'
    $marker = Join-Path $InstallDirectory '.devbox-installed'
    $launcher = Join-Path $InstallDirectory 'devbox.cmd'
    $existing = Get-Command devbox -ErrorAction SilentlyContinue
    $existingPath = if ($existing) { $existing.Path } else { $null }
    if ($existing -and $existingPath -ne $launcher -and $env:DEVBOX_FORCE -ne '1') { Throw-InstallerError "existing devbox command at $existingPath would be shadowed; set DEVBOX_FORCE=1 to proceed." }
    if ((Test-Path -LiteralPath $scriptPath) -and -not (Test-Path -LiteralPath $marker) -and $env:DEVBOX_FORCE -ne '1') { Throw-InstallerError "$scriptPath is not managed by this installer; set DEVBOX_FORCE=1 to replace it." }
    $temporary = Join-Path $InstallDirectory ('.devbox-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        Get-DevboxSource $temporary
        & $Python.Executable $temporary --help | Out-Null
        if ($LASTEXITCODE -ne 0) { Throw-InstallerError 'downloaded devbox script did not validate.' }
        Move-Item -LiteralPath $temporary -Destination $scriptPath -Force
        $cmd = "@echo off`r`n`"$($Python.Executable)`" `"$scriptPath`" %*`r`n"
        [IO.File]::WriteAllText($launcher, $cmd, [Text.Encoding]::ASCII)
        [IO.File]::WriteAllText($marker, $DevboxSourceUrl, [Text.Encoding]::UTF8)
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}

function Install-Devbox {
    $python = Find-CompatiblePython
    if (-not $python) {
        $plan = Get-PythonInstallPlan
        if (-not $plan) { Throw-InstallerError 'No supported Python package manager found. Install Python 3.9 or newer manually.' }
        Write-InstallerMessage "installing Python with $plan"
        switch ($plan) { 'winget' { Install-PythonWithWinget }; 'choco' { Install-PythonWithChocolatey }; 'scoop' { Install-PythonWithScoop } }
        Refresh-ProcessPath
        $python = Find-CompatiblePython
        if (-not $python) { Throw-InstallerError 'The installed Python is still older than Python 3.9.' }
    }
    $directory = if ($env:DEVBOX_INSTALL_DIR) { $env:DEVBOX_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'Programs\devbox\bin' }
    Install-DevboxLauncher $python $directory
    Add-UserPathEntry $directory
    Write-InstallerMessage "installed $directory\devbox.cmd using $($python.Executable)"
}

if ($env:DEVBOX_INSTALLER_SOURCE_ONLY -ne '1') { Install-Devbox }
