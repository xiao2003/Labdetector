param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe',
  [switch]$SkipBuild,
  [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot 'tmp\build_logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("prepare_release_bundle_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$TranscriptStarted = $false
$CanPause = (-not $NoPause) -and ($Host.Name -eq "ConsoleHost") -and [string]::IsNullOrEmpty($env:CI) -and [string]::IsNullOrEmpty($env:GITHUB_ACTIONS)

try {
  Start-Transcript -Path $LogFile -Force | Out-Null
  $TranscriptStarted = $true
} catch {
}

try {
  $Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
  $PcExe = Join-Path $ProjectRoot 'pc\NeuroLab Hub.exe'
  $LlmExe = Join-Path $ProjectRoot 'pc\NeuroLab Hub LLM.exe'
  $VisionExe = Join-Path $ProjectRoot 'pc\NeuroLab Hub Vision.exe'
  $PiLauncher = Join-Path $ProjectRoot 'pi\start_pi_node.sh'
  $ZipPath = Join-Path $ProjectRoot ("NeuroLab-Hub-v$Version.zip")

  if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build_desktop_exe.ps1') -PythonExe $PythonExe -NoPause
  }

  if (!(Test-Path $PcExe) -or !(Test-Path $LlmExe) -or !(Test-Path $VisionExe)) {
    throw "Desktop executable set not found under pc/."
  }
  if (!(Test-Path $PiLauncher)) {
    throw "Pi launcher not found: $PiLauncher"
  }

  Write-Host ''
  Write-Host 'Main executable:' -ForegroundColor Green
  Write-Host $PcExe -ForegroundColor Green
  Write-Host 'LLM executable:' -ForegroundColor Green
  Write-Host $LlmExe -ForegroundColor Green
  Write-Host 'Vision executable:' -ForegroundColor Green
  Write-Host $VisionExe -ForegroundColor Green
  Write-Host 'PI launcher:' -ForegroundColor Green
  Write-Host $PiLauncher -ForegroundColor Green
  Write-Host 'Zip package:' -ForegroundColor Green
  Write-Host $ZipPath -ForegroundColor Green
  Write-Host 'Build log:' -ForegroundColor Green
  Write-Host $LogFile -ForegroundColor Green
}
catch {
  Write-Host ''
  Write-Host "发布包准备失败: $($_.Exception.Message)" -ForegroundColor Red
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