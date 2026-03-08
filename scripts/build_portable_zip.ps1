param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe',
  [switch]$SkipDesktopBuild,
  [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot 'tmp\build_logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("build_portable_zip_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$TranscriptStarted = $false
$CanPause = (-not $NoPause) -and ($Host.Name -eq 'ConsoleHost') -and [string]::IsNullOrEmpty($env:CI) -and [string]::IsNullOrEmpty($env:GITHUB_ACTIONS)

try {
  Start-Transcript -Path $LogFile -Force | Out-Null
  $TranscriptStarted = $true
} catch {
}

try {
  $Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
  $PcRoot = Join-Path $ProjectRoot 'pc'
  $PcExe = Join-Path $PcRoot 'LabDetector.exe'
  $PcApp = Join-Path $PcRoot 'APP'
  $StageRoot = Join-Path $ProjectRoot '.portable_stage'
  $PortableRoot = Join-Path $StageRoot 'LabDetector'
  $PortableZip = Join-Path $ProjectRoot ("LabDetector-Portable-v$Version.zip")

  if ((!(Test-Path $PcExe)) -or (!(Test-Path $PcApp))) {
    if ($SkipDesktopBuild) {
      throw "Desktop runtime not found under: $PcRoot"
    }

    & (Join-Path $PSHOME 'powershell.exe') -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\build_desktop_exe.ps1') -PythonExe $PythonExe -NoPause
    if ($LASTEXITCODE -ne 0) {
      throw 'Desktop build failed while preparing portable zip.'
    }
  }

  foreach ($artifact in @($StageRoot, $PortableZip)) {
    if (Test-Path $artifact) {
      Remove-Item -Recurse -Force $artifact
    }
  }

  New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
  Copy-Item -Path $PcExe -Destination (Join-Path $PortableRoot 'LabDetector.exe') -Force
  Copy-Item -Path $PcApp -Destination (Join-Path $PortableRoot 'APP') -Recurse -Force

  $quickStartLines = @(
    'LabDetector Portable Usage',
    '==========================',
    '1. Unzip this package to any directory.',
    '2. Keep "LabDetector.exe" and "APP" in the same folder.',
    '3. Double-click "LabDetector.exe" to start.',
    '',
    'Note:',
    '- This is a portable package, no installer is required.',
    '- Do not move or delete APP.'
  )
  Set-Content -Path (Join-Path $PortableRoot 'README_PORTABLE.txt') -Value $quickStartLines -Encoding UTF8

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::CreateFromDirectory($PortableRoot, $PortableZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)

  if (Test-Path $StageRoot) {
    Remove-Item -Recurse -Force $StageRoot
  }

  $ExeSizeMB = [math]::Round(((Get-Item $PcExe).Length / 1MB), 2)
  $ZipSizeMB = [math]::Round(((Get-Item $PortableZip).Length / 1MB), 2)

  Write-Host ''
  Write-Host 'Portable launcher EXE:' -ForegroundColor Green
  Write-Host $PcExe -ForegroundColor Green
  Write-Host ("EXE size: {0} MB" -f $ExeSizeMB) -ForegroundColor Green
  Write-Host 'Portable zip package:' -ForegroundColor Green
  Write-Host $PortableZip -ForegroundColor Green
  Write-Host ("ZIP size: {0} MB" -f $ZipSizeMB) -ForegroundColor Green
  Write-Host 'Build log:' -ForegroundColor Green
  Write-Host $LogFile -ForegroundColor Green
}
catch {
  Write-Host ''
  Write-Host "便携包构建失败: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "日志文件: $LogFile" -ForegroundColor Yellow
  if ($CanPause) {
    Read-Host '按回车键退出'
  }
  exit 1
}
finally {
  if ($TranscriptStarted) {
    Stop-Transcript | Out-Null
  }
}
