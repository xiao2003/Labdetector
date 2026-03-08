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
  $PiRoot = Join-Path $ProjectRoot 'pi'
  $PcApp = Join-Path $PcRoot 'APP'
  $PiApp = Join-Path $PiRoot 'APP'
  $StageRoot = Join-Path $ProjectRoot '.portable_stage'
  $PortableRoot = Join-Path $StageRoot 'LabDetector'
  $PortablePcRoot = Join-Path $PortableRoot 'pc'
  $PortablePiRoot = Join-Path $PortableRoot 'pi'
  $PortableZip = Join-Path $ProjectRoot ("LabDetector-Portable-v$Version.zip")

  $RequiredPcFiles = @(
    (Join-Path $PcRoot 'LabDetector.exe'),
    (Join-Path $PcRoot 'LabDetectorTraining.exe'),
    (Join-Path $PcRoot 'Lab.exe'),
    (Join-Path $PcRoot 'LabTraining.exe')
  )
  $NeedBuild = $false
  foreach ($file in $RequiredPcFiles) {
    if (!(Test-Path $file)) {
      $NeedBuild = $true
      break
    }
  }
  if (!(Test-Path $PcApp) -or !(Test-Path $PiApp)) {
    $NeedBuild = $true
  }

  if ($NeedBuild) {
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

  New-Item -ItemType Directory -Force -Path $PortablePcRoot | Out-Null
  New-Item -ItemType Directory -Force -Path $PortablePiRoot | Out-Null

  foreach ($launcher in @('LabDetector.exe', 'LabDetectorPanel.exe', 'LabDetectorTraining.exe', 'Lab.exe', 'LabPanel.exe', 'LabTraining.exe')) {
    $source = Join-Path $PcRoot $launcher
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $PortablePcRoot $launcher) -Force
    }
  }
  Copy-Item -Path $PcApp -Destination (Join-Path $PortablePcRoot 'APP') -Recurse -Force
  Copy-Item -Path (Join-Path $PiRoot 'start_pi_node.sh') -Destination (Join-Path $PortablePiRoot 'start_pi_node.sh') -Force
  Copy-Item -Path $PiApp -Destination (Join-Path $PortablePiRoot 'APP') -Recurse -Force

  $quickStartLines = @(
    'LabDetector Portable Usage',
    '==========================',
    '1. 解压后，PC 端运行 pc\\Lab.exe 或 pc\\LabDetector.exe。',
    '2. 训练工作台运行 pc\\LabTraining.exe。',
    '3. 树莓派端复制 pi 目录后运行 pi/start_pi_node.sh start。',
    '4. 首次运行时建议先执行软件自检，按需自动安装依赖。',
    '',
    '注意：',
    '- pc\\APP 与 pi\\APP 为运行时目录，请勿删除。',
    '- 本包为解压即用版，不包含 Windows 安装流程。',
    '- 如需安装向导，请使用 LabDetector-Setup-v*.exe。'
  )
  Set-Content -Path (Join-Path $PortableRoot 'README_PORTABLE.txt') -Value $quickStartLines -Encoding UTF8

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::CreateFromDirectory($PortableRoot, $PortableZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)

  if (Test-Path $StageRoot) {
    Remove-Item -Recurse -Force $StageRoot
  }

  $ExeSizeMB = [math]::Round(((Get-Item (Join-Path $PcRoot 'Lab.exe')).Length / 1MB), 2)
  $ZipSizeMB = [math]::Round(((Get-Item $PortableZip).Length / 1MB), 2)

  Write-Host ''
  Write-Host 'Portable launcher EXE:' -ForegroundColor Green
  Write-Host (Join-Path $PcRoot 'Lab.exe') -ForegroundColor Green
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
