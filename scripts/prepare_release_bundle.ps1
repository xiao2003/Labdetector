param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe',
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
$ReleaseRoot = Join-Path $ProjectRoot 'release\LabDetector'
$ZipPath = Join-Path $ProjectRoot ("release\LabDetector-v$Version.zip")

if (-not $SkipBuild) {
  & (Join-Path $PSScriptRoot 'build_desktop_exe.ps1') -PythonExe $PythonExe
}

if (!(Test-Path $ReleaseRoot)) {
  throw "Release directory not found: $ReleaseRoot"
}

if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($ReleaseRoot, $ZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)

Write-Host ''
Write-Host 'Release root:' -ForegroundColor Green
Write-Host $ReleaseRoot -ForegroundColor Green
Write-Host 'PC executable:' -ForegroundColor Green
Write-Host (Join-Path $ReleaseRoot 'pc\LabDetector.exe') -ForegroundColor Green
Write-Host 'PI launcher:' -ForegroundColor Green
Write-Host (Join-Path $ReleaseRoot 'pi\start_pi_node.sh') -ForegroundColor Green
Write-Host 'Zip package:' -ForegroundColor Green
Write-Host $ZipPath -ForegroundColor Green
