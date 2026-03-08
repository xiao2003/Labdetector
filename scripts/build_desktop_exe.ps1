param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe',
  [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot 'tmp\build_logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("build_desktop_exe_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$TranscriptStarted = $false
$CanPause = (-not $NoPause) -and ($Host.Name -eq "ConsoleHost") -and [string]::IsNullOrEmpty($env:CI) -and [string]::IsNullOrEmpty($env:GITHUB_ACTIONS)

try {
  Start-Transcript -Path $LogFile -Force | Out-Null
  $TranscriptStarted = $true
} catch {
}

try {
  $Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
  $WorkRoot = Join-Path $ProjectRoot '.pyi_work'
  $DistRoot = Join-Path $ProjectRoot '.pyi_dist'
  $BundleStageRoot = Join-Path $ProjectRoot '.bundle_stage'
  $BundleRoot = Join-Path $BundleStageRoot 'LabDetector'
  $PcRoot = Join-Path $ProjectRoot 'pc'
  $PiRoot = Join-Path $ProjectRoot 'pi'
  $PcExePath = Join-Path $PcRoot 'LabDetector.exe'
  $PcPanelExePath = Join-Path $PcRoot 'LabDetectorPanel.exe'
  $PcTrainingExePath = Join-Path $PcRoot 'LabDetectorTraining.exe'
  $PcAliasExePath = Join-Path $PcRoot 'Lab.exe'
  $PcPanelAliasExePath = Join-Path $PcRoot 'LabPanel.exe'
  $PcTrainingAliasExePath = Join-Path $PcRoot 'LabTraining.exe'
  $PcAppRoot = Join-Path $PcRoot 'APP'
  $PcPythonRuntimeRoot = Join-Path $PcAppRoot 'python_runtime'
  $PcTrainingRuntimeRoot = Join-Path $PcAppRoot 'training_runtime'
  $PiAppRoot = Join-Path $PiRoot 'APP'
  $ZipPath = Join-Path $ProjectRoot ("LabDetector-v$Version.zip")
  $StageFolder = Join-Path $DistRoot 'LabDetector'

  if (!(Test-Path $PythonExe)) {
    $resolvedPython = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($resolvedPython -and $resolvedPython.Source) {
      $PythonExe = $resolvedPython.Source
    }
  }
  if (!(Test-Path $PythonExe)) {
    throw "Python interpreter not found: $PythonExe"
  }
  $PythonHome = Split-Path -Parent $PythonExe

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

  foreach ($path in @($WorkRoot, $DistRoot, $BundleStageRoot)) {
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

  foreach ($artifact in @($PcExePath, $PcPanelExePath, $PcTrainingExePath, $PcAliasExePath, $PcPanelAliasExePath, $PcTrainingAliasExePath, $PcAppRoot, $PiAppRoot, $BundleRoot, $ZipPath)) {
    if (Test-Path $artifact) {
      Remove-Item -Recurse -Force $artifact
    }
  }

  Copy-Item -Path (Join-Path $StageFolder 'LabDetector.exe') -Destination $PcExePath -Force
  Copy-Item -Path $PcExePath -Destination $PcPanelExePath -Force
  Copy-Item -Path $PcExePath -Destination $PcTrainingExePath -Force
  Copy-Item -Path $PcExePath -Destination $PcAliasExePath -Force
  Copy-Item -Path $PcPanelExePath -Destination $PcPanelAliasExePath -Force
  Copy-Item -Path $PcTrainingExePath -Destination $PcTrainingAliasExePath -Force
  Copy-Item -Path (Join-Path $StageFolder 'APP') -Destination $PcAppRoot -Recurse -Force

  New-Item -ItemType Directory -Force -Path $PcPythonRuntimeRoot | Out-Null
  foreach ($file in @('python.exe', 'pythonw.exe', 'python311.dll', 'python3.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll', 'MSVCP140.dll')) {
    $source = Join-Path $PythonHome $file
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $PcPythonRuntimeRoot $file) -Force
    }
  }
  foreach ($dirName in @('Lib', 'DLLs')) {
    $sourceDir = Join-Path $PythonHome $dirName
    if (Test-Path $sourceDir) {
      Copy-Item -Path $sourceDir -Destination (Join-Path $PcPythonRuntimeRoot $dirName) -Recurse -Force
    }
  }
  foreach ($trimPath in @(
    (Join-Path $PcPythonRuntimeRoot 'Lib\site-packages'),
    (Join-Path $PcPythonRuntimeRoot 'Lib\test'),
    (Join-Path $PcPythonRuntimeRoot 'Lib\idlelib'),
    (Join-Path $PcPythonRuntimeRoot 'Lib\tkinter\test')
  )) {
    if (Test-Path $trimPath) {
      Remove-Item -Recurse -Force $trimPath
    }
  }
  Get-ChildItem -Path $PcPythonRuntimeRoot -Directory -Recurse -Force -Filter '__pycache__' | Remove-Item -Recurse -Force
  Get-ChildItem -Path $PcPythonRuntimeRoot -Recurse -Force -Include *.pyc,*.pyo | Remove-Item -Force

  New-Item -ItemType Directory -Force -Path $PcTrainingRuntimeRoot | Out-Null
  foreach ($file in @('training_worker.py', 'llm_finetune.py', 'pi_detector_finetune.py')) {
    $source = Join-Path $ProjectRoot (Join-Path 'pc\training' $file)
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $PcTrainingRuntimeRoot $file) -Force
    }
  }

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
    $source = Join-Path $PiRoot $item
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $PiAppRoot $item) -Recurse -Force
    }
  }
  Copy-Item -Path (Join-Path $ProjectRoot 'VERSION') -Destination (Join-Path $PiAppRoot 'VERSION') -Force

  Get-ChildItem -Path $PiAppRoot -Directory -Recurse -Force -Filter '__pycache__' | Remove-Item -Recurse -Force
  Get-ChildItem -Path $PiAppRoot -Recurse -Force -Include *.pyc,*.pyo | Remove-Item -Force

  $BundlePcRoot = Join-Path $BundleRoot 'pc'
  $BundlePiRoot = Join-Path $BundleRoot 'pi'
  New-Item -ItemType Directory -Force -Path $BundlePcRoot | Out-Null
  New-Item -ItemType Directory -Force -Path $BundlePiRoot | Out-Null
  foreach ($launcher in @('LabDetector.exe', 'LabDetectorPanel.exe', 'LabDetectorTraining.exe', 'Lab.exe', 'LabPanel.exe', 'LabTraining.exe')) {
    $source = Join-Path $PcRoot $launcher
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $BundlePcRoot $launcher) -Force
    }
  }
  Copy-Item -Path $PcAppRoot -Destination (Join-Path $BundlePcRoot 'APP') -Recurse -Force
  Copy-Item -Path (Join-Path $PiRoot 'start_pi_node.sh') -Destination (Join-Path $BundlePiRoot 'start_pi_node.sh') -Force
  Copy-Item -Path $PiAppRoot -Destination (Join-Path $BundlePiRoot 'APP') -Recurse -Force

  $quickStartLines = @(
    'LabDetector Quick Start',
    '=======================',
    '1. PC 端使用 pc\\Lab.exe 或 pc\\LabDetector.exe 启动主程序。',
    '2. 训练工作台使用 pc\\LabTraining.exe 或 pc\\LabDetectorTraining.exe 启动。',
    '3. 树莓派端将 pi 目录复制到设备后，执行 pi/start_pi_node.sh start。',
    '4. 首次运行时先执行软件自检，按需自动安装依赖。',
    '',
    '目录说明：',
    '- pc\\APP 为隐藏运行时目录，请勿删除。',
    '- pi\\APP 为树莓派运行时目录。',
    '- 如需安装到 Windows，请使用 LabDetector-Setup-v*.exe。'
  )
  Set-Content -Path (Join-Path $BundleRoot 'README_QUICKSTART.txt') -Value $quickStartLines -Encoding UTF8

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::CreateFromDirectory($BundleRoot, $ZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)

  if (Test-Path $PcAppRoot) {
    attrib +h +s $PcAppRoot | Out-Null
  }
  if (Test-Path $PiAppRoot) {
    attrib +h +s $PiAppRoot | Out-Null
  }

  foreach ($artifact in @(
    $WorkRoot,
    $DistRoot,
    $BundleStageRoot,
    (Join-Path $ProjectRoot 'build'),
    (Join-Path $ProjectRoot 'dist'),
    (Join-Path $ProjectRoot 'release')
  )) {
    if (Test-Path $artifact) {
      Remove-Item -Recurse -Force $artifact
    }
  }

  Write-Host ''
  Write-Host 'PC executable:' -ForegroundColor Green
  Write-Host $PcExePath -ForegroundColor Green
  Write-Host 'PC alias executable:' -ForegroundColor Green
  Write-Host $PcAliasExePath -ForegroundColor Green
  Write-Host 'Training executable:' -ForegroundColor Green
  Write-Host $PcTrainingExePath -ForegroundColor Green
  Write-Host 'Training alias executable:' -ForegroundColor Green
  Write-Host $PcTrainingAliasExePath -ForegroundColor Green
  Write-Host 'PC runtime:' -ForegroundColor Green
  Write-Host $PcAppRoot -ForegroundColor Green
  Write-Host 'PI launcher:' -ForegroundColor Green
  Write-Host (Join-Path $PiRoot 'start_pi_node.sh') -ForegroundColor Green
  Write-Host 'PI runtime:' -ForegroundColor Green
  Write-Host $PiAppRoot -ForegroundColor Green
  Write-Host 'Zip package:' -ForegroundColor Green
  Write-Host $ZipPath -ForegroundColor Green
  Write-Host 'Build log:' -ForegroundColor Green
  Write-Host $LogFile -ForegroundColor Green
}
catch {
  Write-Host ''
  Write-Host "桌面构建失败: $($_.Exception.Message)" -ForegroundColor Red
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
