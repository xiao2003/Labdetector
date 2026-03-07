param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe',
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
$PcExe = Join-Path $ProjectRoot 'pc\LabDetector.exe'
$PiLauncher = Join-Path $ProjectRoot 'pi\start_pi_node.sh'
$ZipPath = Join-Path $ProjectRoot ("LabDetector-v$Version.zip")

if (-not $SkipBuild) {
  & (Join-Path $PSScriptRoot 'build_desktop_exe.ps1') -PythonExe $PythonExe
}

if (!(Test-Path $PcExe)) {
  throw "Desktop executable not found: $PcExe"
}
if (!(Test-Path $PiLauncher)) {
  throw "Pi launcher not found: $PiLauncher"
}

Write-Host ''
Write-Host 'PC executable:' -ForegroundColor Green
Write-Host $PcExe -ForegroundColor Green
Write-Host 'PI launcher:' -ForegroundColor Green
Write-Host $PiLauncher -ForegroundColor Green
Write-Host 'Zip package:' -ForegroundColor Green
Write-Host $ZipPath -ForegroundColor Green
