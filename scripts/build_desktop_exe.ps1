param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
$WorkRoot = Join-Path $ProjectRoot '.pyi_work'
$DistRoot = Join-Path $ProjectRoot '.pyi_dist'
$ReleaseRoot = Join-Path $ProjectRoot 'release\LabDetector'
$PcReleaseRoot = Join-Path $ReleaseRoot 'pc'
$PiReleaseRoot = Join-Path $ReleaseRoot 'pi'
$PcAppRoot = Join-Path $PcReleaseRoot 'APP'
$PiAppRoot = Join-Path $PiReleaseRoot 'APP'
$ZipPath = Join-Path $ProjectRoot ("release\LabDetector-v$Version.zip")
$StageFolder = Join-Path $DistRoot 'LabDetector'

if (!(Test-Path $PythonExe)) {
  throw "Python interpreter not found: $PythonExe"
}

& $PythonExe (Join-Path $ProjectRoot 'scripts\generate_brand_assets.py')
if ($LASTEXITCODE -ne 0) {
  throw "Brand asset generation failed."
}
& $PythonExe (Join-Path $ProjectRoot 'scripts\write_version_info.py')
if ($LASTEXITCODE -ne 0) {
  throw "Version resource generation failed."
}
$ConfigBootstrap = @"
import sys
sys.path.insert(0, r'$ProjectRoot')
from pc.core import config as _
from pi.config import PiConfig
PiConfig.init()
"@
& $PythonExe -c $ConfigBootstrap
if ($LASTEXITCODE -ne 0) {
  throw "Default config bootstrap failed."
}
& $PythonExe -m pip show pyinstaller | Out-Null
if ($LASTEXITCODE -ne 0) {
  & $PythonExe -m pip install pyinstaller
}

foreach ($path in @($WorkRoot, $DistRoot)) {
  if (Test-Path $path) {
    Remove-Item -Recurse -Force $path
  }
  New-Item -ItemType Directory -Force -Path $path | Out-Null
}

Push-Location $ProjectRoot
try {
  & $PythonExe -m PyInstaller --noconfirm --clean --workpath $WorkRoot --distpath $DistRoot labdetector.spec
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
  }
}
finally {
  Pop-Location
}

if (!(Test-Path $StageFolder)) {
  throw "Build output not found: $StageFolder"
}

if (Test-Path $ReleaseRoot) {
  Remove-Item -Recurse -Force $ReleaseRoot
}
New-Item -ItemType Directory -Force -Path $PcReleaseRoot | Out-Null
New-Item -ItemType Directory -Force -Path $PiReleaseRoot | Out-Null

Copy-Item -Path $StageFolder\* -Destination $PcReleaseRoot -Recurse -Force

$PiSourceRoot = Join-Path $ProjectRoot 'pi'
$PiItems = @(
  'config.ini',
  'config.py',
  'pisend_receive.py',
  'pi_cli.py',
  'setup.py',
  'edge_vision',
  'tools',
  'voice'
)
New-Item -ItemType Directory -Force -Path $PiAppRoot | Out-Null
foreach ($item in $PiItems) {
  $source = Join-Path $PiSourceRoot $item
  if (Test-Path $source) {
    Copy-Item -Path $source -Destination (Join-Path $PiAppRoot $item) -Recurse -Force
  }
}
Copy-Item -Path (Join-Path $ProjectRoot 'VERSION') -Destination (Join-Path $PiAppRoot 'VERSION') -Force

$PiLauncher = @'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/APP/pi_cli.py" "$@"
'@
Set-Content -Path (Join-Path $PiReleaseRoot 'start_pi_node.sh') -Value $PiLauncher -Encoding UTF8

Get-ChildItem -Path $PiReleaseRoot -Directory -Recurse -Force -Filter '__pycache__' | Remove-Item -Recurse -Force
Get-ChildItem -Path $PiReleaseRoot -Recurse -Force -Include *.pyc,*.pyo | Remove-Item -Force

if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($ReleaseRoot, $ZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)

if (Test-Path $PcAppRoot) {
  attrib +h +s $PcAppRoot | Out-Null
}

foreach ($artifact in @(
  $WorkRoot,
  $DistRoot,
  (Join-Path $ProjectRoot 'build'),
  (Join-Path $ProjectRoot 'dist')
)) {
  if (Test-Path $artifact) {
    Remove-Item -Recurse -Force $artifact
  }
}

Write-Host ''
Write-Host 'PC release:' -ForegroundColor Green
Write-Host $PcReleaseRoot -ForegroundColor Green
Write-Host 'PC executable:' -ForegroundColor Green
Write-Host (Join-Path $PcReleaseRoot 'LabDetector.exe') -ForegroundColor Green
Write-Host 'PI release:' -ForegroundColor Green
Write-Host $PiReleaseRoot -ForegroundColor Green
Write-Host 'PI launcher:' -ForegroundColor Green
Write-Host (Join-Path $PiReleaseRoot 'start_pi_node.sh') -ForegroundColor Green
Write-Host 'Zip package:' -ForegroundColor Green
Write-Host $ZipPath -ForegroundColor Green
