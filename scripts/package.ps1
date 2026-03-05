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
    "VERSION",
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

$versionText = (Get-Content -Path "VERSION" -Raw -Encoding UTF8).Trim()
$versionNumber = 0
if (-not [int]::TryParse($versionText, [ref]$versionNumber)) {
    throw "Invalid VERSION file: expected integer, got '$versionText'"
}
if (-not $info.PSObject.Properties.Match("version")) {
    throw "Invalid info.json: missing version field"
}
if ([int]$info.version -ne $versionNumber) {
    throw "Version mismatch: info.json version=$($info.version), VERSION=$versionNumber"
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
