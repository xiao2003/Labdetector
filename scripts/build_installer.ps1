param(
  [string]$InnoCompilerPath = "",
  [switch]$SkipDesktopBuild,
  [string]$PythonExe = "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe",
  [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot 'tmp\build_logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("build_installer_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$TranscriptStarted = $false
$CanPause = (-not $NoPause) -and ($Host.Name -eq "ConsoleHost") -and [string]::IsNullOrEmpty($env:CI) -and [string]::IsNullOrEmpty($env:GITHUB_ACTIONS)

try {
  Start-Transcript -Path $LogFile -Force | Out-Null
  $TranscriptStarted = $true
} catch {
}

try {
  $Version = (Get-Content -Path (Join-Path $ProjectRoot "VERSION") -Raw).Trim()
  $ReleaseRoot = Join-Path $ProjectRoot "pc"
  $DesktopExe = Join-Path $ReleaseRoot "NeuroLab Hub.exe"
  $LlmExe = Join-Path $ReleaseRoot "NeuroLab Hub LLM.exe"
  $VisionExe = Join-Path $ReleaseRoot "NeuroLab Hub Vision.exe"
  $InstallerScript = Join-Path $ProjectRoot "installer\LabDetector.iss"
  $InstallerOutput = Join-Path $ProjectRoot ("NeuroLab-Hub-Setup-v$Version.exe")

  if (!(Test-Path $InstallerScript)) {
    throw "Installer script not found: $InstallerScript"
  }

  if (!(Test-Path $DesktopExe) -or !(Test-Path $LlmExe) -or !(Test-Path $VisionExe)) {
    if ($SkipDesktopBuild) {
      throw "Desktop EXE set not found under: $ReleaseRoot"
    }
    & (Join-Path $PSHOME 'powershell.exe') -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\build_desktop_exe.ps1') -PythonExe $PythonExe -NoPause
  }

  if (!(Test-Path $ReleaseRoot)) {
    throw "Desktop directory not found: $ReleaseRoot"
  }

  if ([string]::IsNullOrWhiteSpace($InnoCompilerPath)) {
    $candidates = @(
      'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
      'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    foreach ($candidate in $candidates) {
      if (Test-Path $candidate) {
        $InnoCompilerPath = $candidate
        break
      }
    }
  }

  if ([string]::IsNullOrWhiteSpace($InnoCompilerPath) -or !(Test-Path $InnoCompilerPath)) {
    throw "ISCC.exe not found. Install Inno Setup 6.x first or pass -InnoCompilerPath. Download: https://jrsoftware.org/isdl.php"
  }

  if (Test-Path $InstallerOutput) {
    Remove-Item -Force $InstallerOutput
  }

  Push-Location $ProjectRoot
  try {
    & $InnoCompilerPath "/DMyAppVersion=$Version" "/DReleaseDir=$ReleaseRoot" $InstallerScript
  }
  finally {
    Pop-Location
  }

  if (!(Test-Path $InstallerOutput)) {
    throw "Installer build failed: $InstallerOutput"
  }

  Write-Host ''
  Write-Host 'Installer output:' -ForegroundColor Green
  Write-Host $InstallerOutput -ForegroundColor Green
  Write-Host 'Installer source:' -ForegroundColor Green
  Write-Host $ReleaseRoot -ForegroundColor Green
  Write-Host 'Build log:' -ForegroundColor Green
  Write-Host $LogFile -ForegroundColor Green
}
catch {
  Write-Host ''
  Write-Host "安装包构建失败: $($_.Exception.Message)" -ForegroundColor Red
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