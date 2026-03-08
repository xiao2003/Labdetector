param(
  [string]$Version = "6.7.1",
  [string]$DownloadUrl = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_1/innosetup-6.7.1.exe",
  [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot 'tmp\build_logs'
$TmpDir = Join-Path $ProjectRoot 'tmp'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
$LogFile = Join-Path $LogDir ("install_inno_setup_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$TranscriptStarted = $false
$CanPause = (-not $NoPause) -and ($Host.Name -eq "ConsoleHost") -and [string]::IsNullOrEmpty($env:CI) -and [string]::IsNullOrEmpty($env:GITHUB_ACTIONS)
$InstallerPath = Join-Path $TmpDir ("innosetup-$Version.exe")

try {
  Start-Transcript -Path $LogFile -Force | Out-Null
  $TranscriptStarted = $true
} catch {
}

try {
  $candidates = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
  )

  Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallerPath
  Start-Process -FilePath $InstallerPath -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-' -Wait

  $found = $null
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      $found = $candidate
      break
    }
  }

  if (-not $found) {
    throw '已完成 Inno Setup 安装，但未找到 ISCC.exe。'
  }

  Write-Host 'Inno Setup 编译器:' -ForegroundColor Green
  Write-Host $found -ForegroundColor Green
  Write-Host 'Install log:' -ForegroundColor Green
  Write-Host $LogFile -ForegroundColor Green
}
catch {
  Write-Host ''
  Write-Host "安装 Inno Setup 失败: $($_.Exception.Message)" -ForegroundColor Red
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


