<#
.SYNOPSIS
    Downloads and installs the pinned LGPL FFmpeg runtime for Windows x64.

.DESCRIPTION
    Verifies the source archive and each installed runtime file. Only ffmpeg,
    ffprobe, their shared FFmpeg libraries and the license text are extracted.
    Existing runtime folders are never overwritten.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-ChildPath([string]$Parent, [string]$Candidate, [string]$Label) {
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\')
    $candidateFull = [System.IO.Path]::GetFullPath($Candidate)
    if (-not $candidateFull.StartsWith($parentFull + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label resolved outside the project-controlled directory: $candidateFull"
    }
    return $candidateFull
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$manifestPath = Join-Path $projectRoot 'resources/native/ffmpeg/manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1 -or $manifest.architecture -ne 'win64') {
    throw "Unsupported FFmpeg manifest: $manifestPath"
}
if ([string]$manifest.archive.url -notmatch '^https://github\.com/BtbN/FFmpeg-Builds/releases/download/') {
    throw 'The pinned FFmpeg URL is outside the approved provider release host.'
}

$vendorRoot = Assert-ChildPath $projectRoot (Join-Path $projectRoot 'vendor') 'Vendor directory'
$targetDirectory = Assert-ChildPath $vendorRoot (Join-Path $vendorRoot 'ffmpeg') 'Runtime directory'
$targetBin = Join-Path $targetDirectory 'bin'
$allFilesMatch = (Test-Path -LiteralPath $targetBin -PathType Container)
if ($allFilesMatch) {
    foreach ($binary in $manifest.binaries) {
        $installed = Join-Path $targetBin ([string]$binary.name)
        if (-not (Test-Path -LiteralPath $installed -PathType Leaf) -or
            (Get-Sha256 $installed) -ne ([string]$binary.sha256).ToLowerInvariant() -or
            (Get-Item -LiteralPath $installed).Length -ne [long]$binary.size_bytes) {
            $allFilesMatch = $false
            break
        }
    }
    $licensePath = Join-Path $targetDirectory 'LICENSE.txt'
    if (-not (Test-Path -LiteralPath $licensePath -PathType Leaf) -or
        (Get-Item -LiteralPath $licensePath).Length -ne [long]$manifest.license.size_bytes -or
        (Get-Sha256 $licensePath) -ne ([string]$manifest.license.sha256).ToLowerInvariant()) {
        $allFilesMatch = $false
    }
}
if ($allFilesMatch) {
    Write-Host "Verified FFmpeg runtime already present: $targetDirectory"
    exit 0
}
if (Test-Path -LiteralPath $targetDirectory) {
    throw "Refusing to replace an existing FFmpeg runtime directory: $targetDirectory"
}

$cacheDirectory = Assert-ChildPath $projectRoot (Join-Path $projectRoot '.local/native/ffmpeg') 'Download cache'
New-Item -ItemType Directory -Path $cacheDirectory -Force | Out-Null
$archivePath = Join-Path $cacheDirectory ([string]$manifest.archive.name)
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    Write-Host "Downloading pinned FFmpeg archive from $($manifest.archive.url)"
    Invoke-WebRequest -Uri ([string]$manifest.archive.url) -OutFile $archivePath
}
if ((Get-Item -LiteralPath $archivePath).Length -ne [long]$manifest.archive.size_bytes -or
    (Get-Sha256 $archivePath) -ne ([string]$manifest.archive.sha256).ToLowerInvariant()) {
    throw 'FFmpeg archive size or SHA-256 does not match the pinned manifest.'
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
New-Item -ItemType Directory -Path $vendorRoot -Force | Out-Null
$staging = Assert-ChildPath $vendorRoot (Join-Path $vendorRoot ('.ffmpeg-staging-' + [guid]::NewGuid().ToString('N'))) 'Staging directory'
New-Item -ItemType Directory -Path (Join-Path $staging 'bin') | Out-Null
try {
    $members = @($manifest.binaries | ForEach-Object { "bin/$($_.name)" }) + @([string]$manifest.license.archive_member)
    foreach ($member in $members) {
        $entryName = ([string]$manifest.archive.archive_prefix) + '/' + $member
        $entry = $archive.GetEntry($entryName)
        if ($null -eq $entry) { throw "Pinned FFmpeg archive is missing $entryName." }
        $leaf = [System.IO.Path]::GetFileName($member)
        $destination = if ($member.StartsWith('bin/')) { Join-Path $staging "bin/$leaf" } else { Join-Path $staging $leaf }
        $safeDestination = Assert-ChildPath $staging $destination 'Extracted file'
        $input = $entry.Open()
        try {
            $output = [System.IO.File]::Open($safeDestination, [System.IO.FileMode]::CreateNew)
            try { $input.CopyTo($output) } finally { $output.Dispose() }
        } finally { $input.Dispose() }
    }
    foreach ($binary in $manifest.binaries) {
        $installed = Join-Path $staging "bin/$($binary.name)"
        if ((Get-Item -LiteralPath $installed).Length -ne [long]$binary.size_bytes -or
            (Get-Sha256 $installed) -ne ([string]$binary.sha256).ToLowerInvariant()) {
            throw "Installed file failed verification: $($binary.name)"
        }
    }
    $stagedLicense = Join-Path $staging 'LICENSE.txt'
    if ((Get-Item -LiteralPath $stagedLicense).Length -ne [long]$manifest.license.size_bytes -or
        (Get-Sha256 $stagedLicense) -ne ([string]$manifest.license.sha256).ToLowerInvariant()) {
        throw 'The extracted FFmpeg license failed size or SHA-256 verification.'
    }
    Move-Item -LiteralPath $staging -Destination $targetDirectory
    Write-Host "Installed verified FFmpeg $($manifest.ffmpeg_version) at $targetDirectory"
}
finally {
    $archive.Dispose()
    if (Test-Path -LiteralPath $staging) {
        $safeStaging = Assert-ChildPath $vendorRoot $staging 'Staging directory cleanup'
        Remove-Item -LiteralPath $safeStaging -Recurse -Force
    }
}
