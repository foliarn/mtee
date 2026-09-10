<#
.SYNOPSIS
    Builds the standalone Windows distribution of MTEE.

.DESCRIPTION
    Runs PyInstaller through uv with the specification of the project and
    checks that dist/MTEE/MTEE.exe was produced. The exit code of the build is
    propagated, so a failure never looks like a success.

.PARAMETER Console
    Keeps the console output of the executable, to diagnose a QML or DLL
    loading problem.

.EXAMPLE
    pwsh -File scripts/build_windows.ps1
#>

[CmdletBinding()]
param(
    [switch]$Console
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$specFile = Join-Path $projectRoot 'packaging/mtee.spec'
$distRoot = Join-Path $projectRoot 'dist'
$workRoot = Join-Path $projectRoot 'build'
$expectedExe = Join-Path $distRoot 'MTEE/MTEE.exe'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error 'uv was not found in PATH. Install uv, then run this script again.'
    exit 1
}

if (-not (Test-Path -LiteralPath $specFile)) {
    Write-Error "Packaging specification not found: $specFile"
    exit 1
}

$env:MTEE_BUILD_CONSOLE = if ($Console) { '1' } else { '0' }

Write-Host "Building MTEE from $projectRoot"
& uv run --frozen pyinstaller --noconfirm --clean `
    --distpath $distRoot `
    --workpath $workRoot `
    $specFile
$buildExitCode = $LASTEXITCODE

if ($buildExitCode -ne 0) {
    Write-Error "PyInstaller failed with exit code $buildExitCode."
    exit $buildExitCode
}

if (-not (Test-Path -LiteralPath $expectedExe)) {
    Write-Error "The build finished but $expectedExe is missing."
    exit 1
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $expectedExe).Length / 1MB, 2)
Write-Host "Built $expectedExe ($sizeMb MB)"
Write-Host 'Check it on a clean Windows machine with: .\dist\MTEE\MTEE.exe --smoke-test'
exit 0
