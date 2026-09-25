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

if (-not (Test-Path -LiteralPath $expectedExe)) {
    Write-Error "The build finished but $expectedExe is missing."
    exit 1
}

# PyInstaller scans PE files declared as data and flattens their imported DLLs
# into _internal. Copy this isolated CLI runtime after the build to retain one
# adjacent copy of each shared library and avoid loading it in MTEE's process.
$packagedFfmpegBin = Join-Path $distRoot 'MTEE/_internal/mtee/native/ffmpeg/bin'
if (Test-Path -LiteralPath $packagedFfmpegBin) {
    Write-Error "Refusing to replace an unexpected packaged FFmpeg directory: $packagedFfmpegBin"
    exit 1
}
New-Item -ItemType Directory -Path $packagedFfmpegBin -Force | Out-Null
foreach ($binary in $ffmpegManifest.binaries) {
    Copy-Item -LiteralPath (Join-Path $ffmpegBin ([string]$binary.name)) `
        -Destination (Join-Path $packagedFfmpegBin ([string]$binary.name))
}

$packagedMpv = @(Get-ChildItem -LiteralPath (Join-Path $distRoot 'MTEE') -Filter 'libmpv-2.dll' -File -Recurse)
if ($packagedMpv.Count -ne 1) {
    Write-Error "Expected exactly one packaged libmpv-2.dll, found $($packagedMpv.Count)."
    exit 1
}
$packagedMpvHash = (Get-FileHash -LiteralPath $packagedMpv[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($packagedMpvHash -ne $expectedMpvHash) {
    Write-Error "The packaged libmpv DLL hash does not match the verified runtime."
    exit 1
}

$packagedFfmpegLicense = Join-Path $distRoot 'MTEE/_internal/mtee/resources/LICENSE.txt'
if (-not (Test-Path -LiteralPath $packagedFfmpegLicense -PathType Leaf) -or
    (Get-FileHash -LiteralPath $packagedFfmpegLicense -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    ([string]$ffmpegManifest.license.sha256).ToLowerInvariant()) {
    Write-Error 'The packaged FFmpeg license text is missing or has the wrong SHA-256.'
    exit 1
}

$packagedFfmpegBin = Join-Path $distRoot 'MTEE/_internal/mtee/native/ffmpeg/bin'
foreach ($binary in $ffmpegManifest.binaries) {
    $packaged = Join-Path $packagedFfmpegBin ([string]$binary.name)
    if (-not (Test-Path -LiteralPath $packaged -PathType Leaf)) {
        Write-Error "The packaged FFmpeg runtime is missing: $packaged"
        exit 1
    }
    if ((Get-FileHash -LiteralPath $packaged -Algorithm SHA256).Hash.ToLowerInvariant() -ne
        ([string]$binary.sha256).ToLowerInvariant()) {
        Write-Error "The packaged FFmpeg runtime failed SHA-256 verification: $packaged"
        exit 1
    }
}
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

$sizeMb = [math]::Round((Get-Item -LiteralPath $expectedExe).Length / 1MB, 2)
Write-Host "Built $expectedExe ($sizeMb MB)"
Write-Host 'Check it on a clean Windows machine with: .\dist\MTEE\MTEE.exe --smoke-test'
exit 0
