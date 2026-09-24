<#
.SYNOPSIS
    Downloads and verifies the pinned LGPL libmpv runtime.

.DESCRIPTION
    The archive is checked before extraction. Only libmpv-2.dll is copied into
    the Git-ignored vendor/mpv directory; the executable and development
    headers are never unpacked into the application runtime.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-ChildPath([string]$Parent, [string]$Candidate, [string]$Label) {
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\')
    $candidateFull = [System.IO.Path]::GetFullPath($Candidate)
    $prefix = $parentFull + '\'
    if (-not $candidateFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label resolved outside the project-controlled directory: $candidateFull"
    }
    return $candidateFull
}

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$manifestPath = Join-Path $projectRoot 'resources/native/mpv/manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1 -or $manifest.architecture -ne 'x86_64') {
    throw "Unsupported libmpv manifest: $manifestPath"
}

$vendorRoot = Assert-ChildPath $projectRoot (Join-Path $projectRoot 'vendor') 'Vendor directory'
$targetDirectory = Assert-ChildPath $vendorRoot (Join-Path $vendorRoot 'mpv') 'Runtime directory'
$targetLibrary = Join-Path $targetDirectory 'libmpv-2.dll'
$expectedLibraryHash = ([string]$manifest.library.sha256).ToLowerInvariant()

if (Test-Path -LiteralPath $targetDirectory) {
    if (Test-Path -LiteralPath $targetLibrary) {
        $existingHash = (Get-FileHash -LiteralPath $targetLibrary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($existingHash -eq $expectedLibraryHash) {
            Write-Host "Verified runtime already present: $targetLibrary"
            exit 0
        }
    }
    throw "Refusing to replace an existing runtime directory: $targetDirectory"
}

$cacheDirectory = Assert-ChildPath $projectRoot (Join-Path $projectRoot '.local/native/mpv') 'Download cache'
New-Item -ItemType Directory -Path $cacheDirectory -Force | Out-Null
$archivePath = Join-Path $cacheDirectory ([string]$manifest.archive.name)
$expectedArchiveHash = ([string]$manifest.archive.sha256).ToLowerInvariant()

if (-not (Test-Path -LiteralPath $archivePath)) {
    Write-Host "Downloading pinned libmpv archive from $($manifest.archive.url)"
    Invoke-WebRequest -Uri ([string]$manifest.archive.url) -OutFile $archivePath
}

$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($archiveHash -ne $expectedArchiveHash) {
    throw "Archive SHA-256 mismatch. Expected $expectedArchiveHash, received $archiveHash."
}

$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
if (-not $tar) {
    throw 'Windows tar.exe (bsdtar with 7z support) is required to extract the verified archive.'
}

New-Item -ItemType Directory -Path $vendorRoot -Force | Out-Null
$stagingDirectory = Assert-ChildPath $vendorRoot (Join-Path $vendorRoot ('.mpv-staging-' + [guid]::NewGuid().ToString('N'))) 'Staging directory'
New-Item -ItemType Directory -Path $stagingDirectory | Out-Null

try {
    & $tar.Source -xf $archivePath -C $stagingDirectory ([string]$manifest.library.archive_member)
    if ($LASTEXITCODE -ne 0) {
        throw "Archive extraction failed with exit code $LASTEXITCODE."
    }
    $stagedLibrary = Join-Path $stagingDirectory 'libmpv-2.dll'
    if (-not (Test-Path -LiteralPath $stagedLibrary -PathType Leaf)) {
        throw 'The pinned archive did not contain libmpv-2.dll at its expected root path.'
    }
    $libraryHash = (Get-FileHash -LiteralPath $stagedLibrary -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($libraryHash -ne $expectedLibraryHash) {
        throw "Extracted DLL SHA-256 mismatch. Expected $expectedLibraryHash, received $libraryHash."
    }
    if (Test-Path -LiteralPath $targetDirectory) {
        throw "Refusing to replace a runtime directory created during extraction: $targetDirectory"
    }
    Move-Item -LiteralPath $stagingDirectory -Destination $targetDirectory
    Write-Host "Installed verified libmpv $($manifest.release_tag) at $targetLibrary"
}
finally {
    if (Test-Path -LiteralPath $stagingDirectory) {
        $safeStaging = Assert-ChildPath $vendorRoot $stagingDirectory 'Staging directory cleanup'
        Remove-Item -LiteralPath $safeStaging -Recurse -Force
    }
}
