<#
.SYNOPSIS
    Builds the standalone Windows distribution of MTEE.

.DESCRIPTION
    Runs PyInstaller through uv with the specification of the project and
    checks that dist/MTEE.exe was produced as a single-file application. The exit code of the build is
    propagated, so a failure never looks like a success.

.PARAMETER Console
    Keeps the console output of the executable, to diagnose a QML or DLL
    loading problem.

.PARAMETER DistDirectory
    Distribution directory, relative to the project root. Defaults to dist.

.PARAMETER WorkDirectory
    PyInstaller work directory, relative to the project root. Defaults to build.

.EXAMPLE
    pwsh -File scripts/build_windows.ps1

.EXAMPLE
    pwsh -File scripts/build_windows.ps1 -DistDirectory dist/fix-build -WorkDirectory build/fix-build
#>

[CmdletBinding()]
param(
    [switch]$Console,
    [string]$DistDirectory = 'dist',
    [string]$WorkDirectory = 'build'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$projectRootPrefix = [IO.Path]::GetFullPath($projectRoot).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
$specFile = Join-Path $projectRoot 'packaging/mtee.spec'
$distRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot $DistDirectory))
$workRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot $WorkDirectory))
if (-not $distRoot.StartsWith($projectRootPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    -not $workRoot.StartsWith($projectRootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Error 'Build output and work directories must stay inside the project root.'
    exit 1
}
$expectedExe = Join-Path $distRoot 'MTEE.exe'
$mpvLibrary = Join-Path $projectRoot 'vendor/mpv/libmpv-2.dll'
$manifestPath = Join-Path $projectRoot 'resources/native/mpv/manifest.json'
$ffmpegManifestPath = Join-Path $projectRoot 'resources/native/ffmpeg/manifest.json'
$ffmpegBin = Join-Path $projectRoot 'vendor/ffmpeg/bin'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error 'uv was not found in PATH. Install uv, then run this script again.'
    exit 1
}

if (-not (Test-Path -LiteralPath $specFile)) {
    Write-Error "Packaging specification not found: $specFile"
    exit 1
}

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    Write-Error "The libmpv manifest is missing: $manifestPath"
    exit 1
}

if (-not (Test-Path -LiteralPath $ffmpegManifestPath -PathType Leaf)) {
    Write-Error "The FFmpeg manifest is missing: $ffmpegManifestPath"
    exit 1
}
$ffmpegManifest = Get-Content -LiteralPath $ffmpegManifestPath -Raw | ConvertFrom-Json
$ffmpegLicensePath = Join-Path (Split-Path -Parent $ffmpegBin) 'LICENSE.txt'
if (-not (Test-Path -LiteralPath $ffmpegLicensePath -PathType Leaf) -or
    (Get-Item -LiteralPath $ffmpegLicensePath).Length -ne [long]$ffmpegManifest.license.size_bytes -or
    (Get-FileHash -LiteralPath $ffmpegLicensePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    ([string]$ffmpegManifest.license.sha256).ToLowerInvariant()) {
    Write-Error 'The FFmpeg license text does not match the pinned manifest.'
    exit 1
}
foreach ($binary in $ffmpegManifest.binaries) {
    $runtimeFile = Join-Path $ffmpegBin ([string]$binary.name)
    if (-not (Test-Path -LiteralPath $runtimeFile -PathType Leaf)) {
        Write-Error "The verified FFmpeg runtime is missing: $runtimeFile. Run scripts/fetch_ffmpeg.ps1 first."
        exit 1
    }
    $runtimeHash = (Get-FileHash -LiteralPath $runtimeFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ((Get-Item -LiteralPath $runtimeFile).Length -ne [long]$binary.size_bytes -or
        $runtimeHash -ne ([string]$binary.sha256).ToLowerInvariant()) {
        Write-Error "The FFmpeg runtime does not match the pinned manifest: $runtimeFile"
        exit 1
    }
}
if (-not (Test-Path -LiteralPath $mpvLibrary -PathType Leaf)) {
    Write-Error "The verified libmpv runtime is missing: $mpvLibrary. Run scripts/fetch_mpv.ps1 first."
    exit 1
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$expectedMpvHash = ([string]$manifest.library.sha256).ToLowerInvariant()
$actualMpvHash = (Get-FileHash -LiteralPath $mpvLibrary -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualMpvHash -ne $expectedMpvHash) {
    Write-Error "The libmpv DLL does not match the manifest: expected $expectedMpvHash, received $actualMpvHash."
    exit 1
}

$verifierScript = Join-Path $projectRoot 'scripts/verify_singlefile.py'
if (-not (Test-Path -LiteralPath $verifierScript -PathType Leaf)) {
    Write-Error "The single-file verification script is missing: $verifierScript"
    exit 1
}

$cacheRoot = Join-Path $projectRoot '.local/uv-cache'
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
$env:UV_CACHE_DIR = $cacheRoot

$env:MTEE_BUILD_CONSOLE = if ($Console) { '1' } else { '0' }

Write-Host "Building MTEE from $projectRoot"
& uv run --no-sync --frozen pyinstaller --noconfirm --clean `
    --distpath $distRoot `
    --workpath $workRoot `
    $specFile
$buildExitCode = $LASTEXITCODE

if ($buildExitCode -ne 0) {
    Write-Error "PyInstaller failed with exit code $buildExitCode."
    exit $buildExitCode
}
if (-not (Test-Path -LiteralPath $expectedExe -PathType Leaf)) {
    Write-Error "The build finished but $expectedExe is missing."
    exit 1
}

$embeddedRuntimeRoot = Join-Path $workRoot 'singlefile-verification'
& uv run --no-sync --frozen python $verifierScript `
    --executable $expectedExe `
    --ffmpeg-manifest $ffmpegManifestPath `
    --mpv-manifest $manifestPath `
    --runtime-root $embeddedRuntimeRoot
$verifyExitCode = $LASTEXITCODE
if ($verifyExitCode -ne 0) {
    Write-Error "The embedded single-file payload failed verification with exit code $verifyExitCode."
    exit $verifyExitCode
}

$packagedFfmpegBin = Join-Path $embeddedRuntimeRoot 'mtee/native/ffmpeg/bin'
$ffmpegVersionOutput = & (Join-Path $packagedFfmpegBin 'ffmpeg.exe') -version 2>&1
$ffmpegVersionExitCode = $LASTEXITCODE
$packagedFfmpegVersion = $ffmpegVersionOutput | Select-Object -First 1
if ($ffmpegVersionExitCode -ne 0 -or $packagedFfmpegVersion -notmatch [regex]::Escape([string]$ffmpegManifest.ffmpeg_version)) {
    Write-Error 'The packaged ffmpeg.exe could not report the pinned runtime version.'
    exit 1
}
$ffprobeVersionOutput = & (Join-Path $packagedFfmpegBin 'ffprobe.exe') -version 2>&1
$ffprobeVersionExitCode = $LASTEXITCODE
$packagedFfprobeVersion = $ffprobeVersionOutput | Select-Object -First 1
if ($ffprobeVersionExitCode -ne 0 -or $packagedFfprobeVersion -notmatch [regex]::Escape([string]$ffmpegManifest.ffmpeg_version)) {
    Write-Error 'The packaged ffprobe.exe could not report the pinned runtime version.'
    exit 1
}

$sizeMib = [math]::Round((Get-Item -LiteralPath $expectedExe).Length / 1MB, 2)
Write-Host "Built $expectedExe ($sizeMib MiB)"
Write-Host 'Smoke-test the single EXE with: .\dist\MTEE.exe --data-dir .local/validation/main-onefile --smoke-test'
exit 0
