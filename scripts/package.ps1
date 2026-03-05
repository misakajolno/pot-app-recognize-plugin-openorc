param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

if (-not (Test-Path "info.json")) {
    throw "info.json not found in project root: $ProjectRoot"
}

$info = Get-Content -Path "info.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$pluginId = [string]$info.id
if ([string]::IsNullOrWhiteSpace($pluginId)) {
    throw "Invalid info.json: missing id"
}
if (-not $pluginId.StartsWith("plugin")) {
    throw "Invalid plugin id '$pluginId': pot plugin package name must start with 'plugin'"
}

$requiredEntries = @(
    "info.json",
    "main.js",
    "README.md",
    "openorc.png",
    "scripts"
)

foreach ($entry in $requiredEntries) {
    if (-not (Test-Path $entry)) {
        throw "Required file missing: $entry"
    }
}

$outputPath = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
} else {
    Join-Path $ProjectRoot $OutputDir
}
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

$packagePath = Join-Path $outputPath ("{0}.potext" -f $pluginId)
if (Test-Path $packagePath) {
    Remove-Item -Path $packagePath -Force
}

Compress-Archive -Path $requiredEntries -DestinationPath $packagePath -CompressionLevel Optimal

$archiveSize = (Get-Item $packagePath).Length
Write-Host "Package created: $packagePath"
Write-Host "Size(bytes): $archiveSize"
Write-Host "Included entries:"
$requiredEntries | ForEach-Object { Write-Host "- $_" }
