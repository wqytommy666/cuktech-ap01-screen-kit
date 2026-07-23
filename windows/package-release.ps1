[CmdletBinding()]
param(
    [string]$Version = "0.4.1",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $SkipBuild) {
    & "$PSScriptRoot\build-app.ps1" -Version $Version
}

$BuiltApp = Join-Path $Root "dist\windows\CUKTECH Screen Controller"
if (-not (Test-Path (Join-Path $BuiltApp "CUKTECH Screen Controller.exe"))) {
    throw "Run windows/build-app.ps1 first."
}

$StageName = "CUKTECH-Screen-Controller-$Version-Windows-x64"
$Stage = Join-Path $Root "dist\$StageName"
$Zip = Join-Path $Root "dist\$StageName.zip"
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
if (Test-Path $Zip) { Remove-Item -Force $Zip }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Copy-Item -Recurse -Force $BuiltApp (Join-Path $Stage "App")
Copy-Item -Force "$PSScriptRoot\Install CUKTECH Screen Controller.cmd" $Stage
Copy-Item -Force "$PSScriptRoot\Install-CUKTECHScreenController.ps1" $Stage
Copy-Item -Force "$PSScriptRoot\Uninstall-CUKTECHScreenController.ps1" $Stage
Copy-Item -Force "$PSScriptRoot\先读我-Windows.txt" $Stage
Copy-Item -Force "$PSScriptRoot\mi-credentials.example.json" $Stage
Copy-Item -Force "$PSScriptRoot\THIRD-PARTY-NOTICES.txt" $Stage
Copy-Item -Force (Join-Path $Root "LICENSE") (Join-Path $Stage "PROJECT-LICENSE.txt")

(Get-Content (Join-Path $Stage "先读我-Windows.txt") -Raw).Replace("{{VERSION}}", $Version) |
    Set-Content -Encoding UTF8 (Join-Path $Stage "先读我-Windows.txt")
(Get-Content (Join-Path $Stage "Install-CUKTECHScreenController.ps1") -Raw).Replace("{{VERSION}}", $Version) |
    Set-Content -Encoding UTF8 (Join-Path $Stage "Install-CUKTECHScreenController.ps1")

@{
    name = "CUKTECH Screen Controller"
    version = $Version
    platform = "Windows x64"
    packager = "PyInstaller"
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Stage "BUILD-MANIFEST.json")

Compress-Archive -Path $Stage -DestinationPath $Zip -CompressionLevel Optimal
$Hash = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLowerInvariant()
"$Hash  $StageName.zip" | Set-Content -Encoding ASCII "$Zip.sha256"
Write-Host "Package: $Zip"
Write-Host "SHA-256: $Hash"
