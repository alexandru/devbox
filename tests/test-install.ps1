$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:DEVBOX_INSTALLER_SOURCE_ONLY = '1'
. "$root/install.ps1"

if (-not (Test-PythonVersion -PythonCommand 'python' -ErrorAction SilentlyContinue)) {
    throw 'Expected the runner Python to satisfy the installer baseline.'
}

$updated = Add-PathEntry -PathValue 'C:\Tools\devbox' -ExistingPath 'C:\Windows;C:\Tools\devbox\'
if ($updated -ne 'C:\Windows;C:\Tools\devbox\') { throw 'PATH entry should be idempotent.' }

Write-Output 'Windows installer tests passed'
