[CmdletBinding()]
param(
    [string]$Version = "0.4.1",
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "CUKTECH Screen Controller · Windows build"
Write-Host "==========================================="

if (Get-Command py -ErrorAction SilentlyContinue) {
    $Launcher = "py"
    $LauncherArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Launcher = "python"
    $LauncherArgs = @()
} else {
    throw "Python 3.10+ was not found."
}

& $Launcher @LauncherArgs -c "import sys; raise SystemExit(sys.version_info < (3, 10))"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or later is required." }

$BuildVenv = Join-Path $Root ".venv-windows-build"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    & $Launcher @LauncherArgs -m venv $BuildVenv
}
if (-not $SkipDependencies) {
    & $Python -m pip install --disable-pip-version-check -r requirements-windows-app.txt
}
& $Python -c "import PIL, PySide6, cryptography, PyInstaller"

$BuildRoot = Join-Path $Root ".build\windows"
$DistRoot = Join-Path $Root "dist\windows"
$Icon = Join-Path $BuildRoot "CUKTECHScreenController.ico"
New-Item -ItemType Directory -Force -Path $BuildRoot, $DistRoot | Out-Null
& $Python -c "from PIL import Image; im=Image.open(r'macos/AP01Logo.png').convert('RGBA'); im.save(r'$Icon', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"

$VersionParts = $Version.Split('.')
while ($VersionParts.Count -lt 4) { $VersionParts += "0" }
$NumericVersion = ($VersionParts[0..3] -join ', ')
$VersionFile = Join-Path $BuildRoot "version-info.txt"
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($NumericVersion), prodvers=($NumericVersion), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('080404b0', [
    StringStruct('CompanyName', 'wqytommy666'),
    StringStruct('FileDescription', 'CUKTECH AP01 Screen Controller'),
    StringStruct('FileVersion', '$Version'),
    StringStruct('InternalName', 'CUKTECH Screen Controller'),
    StringStruct('OriginalFilename', 'CUKTECH Screen Controller.exe'),
    StringStruct('ProductName', 'CUKTECH Screen Controller'),
    StringStruct('ProductVersion', '$Version')
  ])]), VarFileInfo([VarStruct('Translation', [2052, 1200])])]
)
"@ | Set-Content -Encoding UTF8 $VersionFile

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "CUKTECH Screen Controller" `
    --icon $Icon `
    --version-file $VersionFile `
    --paths $Root `
    --distpath $DistRoot `
    --workpath $BuildRoot `
    --specpath $BuildRoot `
    --add-data "macos/AP01Logo.png;macos" `
    --add-data "reference/provider-icons;reference/provider-icons" `
    --hidden-import ap01_prepare_screen `
    --hidden-import ap01_screen_bridge `
    --hidden-import ap01_wifi_bridge `
    --hidden-import quota_dashboard `
    --hidden-import ap01_install_firmware `
    --hidden-import ap01_fds_relay_client `
    --hidden-import ap01_custom_ota `
    --hidden-import mi_cloud `
    --hidden-import patch_asset `
    windows/AP01ScreenController.py

$Exe = Join-Path $DistRoot "CUKTECH Screen Controller\CUKTECH Screen Controller.exe"
if (-not (Test-Path $Exe)) { throw "Build completed without the expected executable: $Exe" }

$Probe = Start-Process -FilePath $Exe -ArgumentList "--diagnose-json" -PassThru -Wait
if ($Probe.ExitCode -ne 0) { throw "The packaged diagnostic exited with code $($Probe.ExitCode)." }
Write-Host "Built: $Exe"
