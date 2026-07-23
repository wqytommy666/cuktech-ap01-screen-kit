[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Version = "{{VERSION}}"
if ($Version.StartsWith("{")) { $Version = "0.4.1" }
$Source = Join-Path $PSScriptRoot "App"
$SourceExe = Join-Path $Source "CUKTECH Screen Controller.exe"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\CUKTECH Screen Controller"
$DataRoot = Join-Path $env:LOCALAPPDATA "CUKTECH Screen Controller"
$TargetExe = Join-Path $InstallRoot "CUKTECH Screen Controller.exe"
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\CUKTECH Screen Controller"
$StartMenu = Join-Path $StartMenuDir "CUKTECH Screen Controller.lnk"
$UninstallShortcut = Join-Path $StartMenuDir "Uninstall CUKTECH Screen Controller.lnk"
$InstalledUninstaller = Join-Path $DataRoot "Uninstall-CUKTECHScreenController.ps1"
$Startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\CUKTECH Screen Controller Bridge.vbs"
$UninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CUKTECHScreenController"

Write-Host "CUKTECH Screen Controller · Windows installer"
Write-Host "=============================================="
if (-not [Environment]::Is64BitOperatingSystem) { throw "This package requires 64-bit Windows 10 or 11." }
if (-not (Test-Path $SourceExe)) { throw "The App directory is incomplete. Extract the whole ZIP before installing." }

Get-Process -Name "CUKTECH Screen Controller" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "CUKTECHRuntime" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
if (Test-Path $InstallRoot) { Remove-Item -Recurse -Force $InstallRoot }
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Copy-Item -Recurse -Force (Join-Path $Source "*") $InstallRoot
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "Uninstall-CUKTECHScreenController.ps1") $InstalledUninstaller
Write-Host "[1/4] Installed application files."

$Shell = New-Object -ComObject WScript.Shell
$LegacyShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\CUKTECH Screen Controller.lnk"
Remove-Item -Force -ErrorAction SilentlyContinue $LegacyShortcut
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$Shortcut = $Shell.CreateShortcut($StartMenu)
$Shortcut.TargetPath = $TargetExe
$Shortcut.WorkingDirectory = $InstallRoot
$Shortcut.IconLocation = "$TargetExe,0"
$Shortcut.Description = "Control the CUKTECH AP01 display"
$Shortcut.Save()
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$RemoveShortcut = $Shell.CreateShortcut($UninstallShortcut)
$RemoveShortcut.TargetPath = $PowerShellExe
$RemoveShortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $InstalledUninstaller + '"'
$RemoveShortcut.WorkingDirectory = $env:TEMP
$RemoveShortcut.IconLocation = "$TargetExe,0"
$RemoveShortcut.Description = "Uninstall CUKTECH Screen Controller"
$RemoveShortcut.Save()
Write-Host "[2/4] Added Start Menu shortcuts."

$Command = '"' + $TargetExe.Replace('"', '""') + '" --bridge'
$Vbs = 'Set shell = CreateObject("WScript.Shell")' + "`r`n" + 'shell.Run "' + $Command.Replace('"', '""') + '", 0, False' + "`r`n"
[System.IO.File]::WriteAllText($Startup, $Vbs, [System.Text.Encoding]::Unicode)
Write-Host "[3/4] Enabled the login background Bridge."

New-Item -Path $UninstallKey -Force | Out-Null
$UninstallCommand = '"' + $PowerShellExe + '" -NoProfile -ExecutionPolicy Bypass -File "' + $InstalledUninstaller + '"'
New-ItemProperty -Path $UninstallKey -Name DisplayName -Value "CUKTECH Screen Controller" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name DisplayVersion -Value $Version -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name Publisher -Value "wqytommy666" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name DisplayIcon -Value $TargetExe -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name InstallLocation -Value $InstallRoot -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name UninstallString -Value $UninstallCommand -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
Write-Host "[4/4] Registered the per-user uninstaller."

Start-Process -FilePath $TargetExe
Write-Host ""
Write-Host "Installed: $TargetExe" -ForegroundColor Green
Write-Host "Open or uninstall it later from the Start Menu."
