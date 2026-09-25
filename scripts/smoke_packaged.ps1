<#
.SYNOPSIS
    Runs the packaged MTEE in smoke test mode and returns its exit code.

.DESCRIPTION
    The distributed executable is a windowed program: started directly from a
    shell it returns at once and its exit code cannot be read. This script waits
    for the process and propagates the real code, so a failed start is never
    reported as a success.

.PARAMETER DataDir
    Directory used for the settings, the cache and the logs of this check.

.EXAMPLE
    pwsh -File scripts/smoke_packaged.ps1 -DataDir .local/validation/01-packaged
#>

[CmdletBinding()]
param(
    [string]$DataDir = '.local/validation/01-packaged'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$executable = Join-Path $projectRoot 'dist/MTEE.exe'

if (-not (Test-Path -LiteralPath $executable)) {
    Write-Error "Distribution not found: $executable. Build it with scripts/build_windows.ps1."
    exit 1
}

$resolvedDataDir = if ([System.IO.Path]::IsPathRooted($DataDir)) {
    $DataDir
} else {
    Join-Path $projectRoot $DataDir
}

Write-Host "Starting $executable --smoke-test"
$process = Start-Process -FilePath $executable `
    -ArgumentList '--data-dir', $resolvedDataDir, '--smoke-test' `
    -Wait -PassThru
$exitCode = $process.ExitCode

if ($exitCode -ne 0) {
    Write-Error "The packaged application exited with code $exitCode."
    exit $exitCode
}

Write-Host 'The packaged application loaded its window and quit with code 0.'
exit 0
