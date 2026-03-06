param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe',
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
$ReleaseRoot = Join-Path $ProjectRoot ("release\LabDetector-v$Version")
$ZipPath = Join-Path $ProjectRoot ("release\LabDetector-v$Version.zip")

if (-not $SkipBuild) {
  & (Join-Path $PSScriptRoot 'build_desktop_exe.ps1') -PythonExe $PythonExe
}

if (!(Test-Path $ReleaseRoot)) {
  throw "未找到正式发布目录: $ReleaseRoot"
}

if (!(Test-Path $ZipPath)) {
  Compress-Archive -Path $ReleaseRoot -DestinationPath $ZipPath -Force
}

Write-Host ''
Write-Host '正式发布目录:' -ForegroundColor Green
Write-Host $ReleaseRoot -ForegroundColor Green
Write-Host '正式运行入口:' -ForegroundColor Green
Write-Host (Join-Path $ReleaseRoot 'LabDetector.exe') -ForegroundColor Green
Write-Host '发布压缩包:' -ForegroundColor Green
Write-Host $ZipPath -ForegroundColor Green
