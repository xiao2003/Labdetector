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
  $BundleRoot = Join-Path $BundleStageRoot 'NeuroLab Hub'
  $PcRoot = Join-Path $ProjectRoot 'pc'
  $PiRoot = Join-Path $ProjectRoot 'pi'
  $PcExePath = Join-Path $PcRoot 'NeuroLab Hub.exe'
  $PcLlmExePath = Join-Path $PcRoot 'NeuroLab Hub LLM.exe'
  $PcVisionExePath = Join-Path $PcRoot 'NeuroLab Hub Vision.exe'
  $PcAppRoot = Join-Path $PcRoot 'APP'
  $PcPythonRuntimeRoot = Join-Path $PcAppRoot 'python_runtime'
  $PcTrainingRuntimeRoot = Join-Path $PcAppRoot 'training_runtime'
  $PiAppRoot = Join-Path $PiRoot 'APP'
  $ZipPath = Join-Path $ProjectRoot ("NeuroLab-Hub-v$Version.zip")
  $StageFolder = Join-Path $DistRoot 'NeuroLab Hub'

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
  & $PythonExe (Join-Path $ProjectRoot 'scripts\check_source_encoding.py')
  if ($LASTEXITCODE -ne 0) {
    throw "Source encoding check failed."
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

  $buildTargets = @(
    @{ Name = 'NeuroLab Hub'; OutDir = $DistRoot },
    @{ Name = 'NeuroLab Hub LLM'; OutDir = (Join-Path $BundleStageRoot 'dist_llm') },
    @{ Name = 'NeuroLab Hub Vision'; OutDir = (Join-Path $BundleStageRoot 'dist_vision') }
  )

  foreach ($target in $buildTargets) {
    $targetDist = $target.OutDir
    if (Test-Path $targetDist) {
      Remove-Item -Recurse -Force $targetDist
    }
    New-Item -ItemType Directory -Force -Path $targetDist | Out-Null

    Push-Location $ProjectRoot
    try {
      $env:NEUROLAB_EXE_NAME = $target.Name
      & $PythonExe -m PyInstaller --noconfirm --clean --workpath $WorkRoot --distpath $targetDist neurolab_hub.spec
      if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed for $($target.Name)."
      }
    }
    finally {
      Remove-Item Env:NEUROLAB_EXE_NAME -ErrorAction SilentlyContinue
      Pop-Location
    }
  }

  if (!(Test-Path $StageFolder)) {
    throw "Build output not found: $StageFolder"
  }

  foreach ($artifact in @($PcExePath, $PcLlmExePath, $PcVisionExePath, $PcAppRoot, $PiAppRoot, $BundleRoot, $ZipPath)) {
    if (Test-Path $artifact) {
      Remove-Item -Recurse -Force $artifact
    }
  }
  foreach ($legacy in @('LabDetector.exe', 'LabDetectorPanel.exe', 'LabDetectorTraining.exe', 'Lab.exe', 'LabPanel.exe', 'LabTraining.exe')) {
    $legacyPath = Join-Path $PcRoot $legacy
    if (Test-Path $legacyPath) {
      Remove-Item -Force $legacyPath
    }
  }

  $LlmStageFolder = Join-Path (Join-Path $BundleStageRoot 'dist_llm') 'NeuroLab Hub LLM'
  $VisionStageFolder = Join-Path (Join-Path $BundleStageRoot 'dist_vision') 'NeuroLab Hub Vision'
  if (!(Test-Path $LlmStageFolder)) {
    throw "Build output not found: $LlmStageFolder"
  }
  if (!(Test-Path $VisionStageFolder)) {
    throw "Build output not found: $VisionStageFolder"
  }

  Copy-Item -Path (Join-Path $StageFolder 'NeuroLab Hub.exe') -Destination $PcExePath -Force
  Copy-Item -Path (Join-Path $LlmStageFolder 'NeuroLab Hub LLM.exe') -Destination $PcLlmExePath -Force
  Copy-Item -Path (Join-Path $VisionStageFolder 'NeuroLab Hub Vision.exe') -Destination $PcVisionExePath -Force
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
  foreach ($launcher in @('NeuroLab Hub.exe', 'NeuroLab Hub LLM.exe', 'NeuroLab Hub Vision.exe')) {
    $source = Join-Path $PcRoot $launcher
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $BundlePcRoot $launcher) -Force
    }
  }
  Copy-Item -Path $PcAppRoot -Destination (Join-Path $BundlePcRoot 'APP') -Recurse -Force
  Copy-Item -Path (Join-Path $PiRoot 'start_pi_node.sh') -Destination (Join-Path $BundlePiRoot 'start_pi_node.sh') -Force
  Copy-Item -Path $PiAppRoot -Destination (Join-Path $BundlePiRoot 'APP') -Recurse -Force

  $quickStartLines = @(
    'NeuroLab Hub Quick Start',
    '========================',
    '1. PC 端使用 pc\\NeuroLab Hub.exe 启动主程序。',
    '2. LLM 微调入口使用 pc\\NeuroLab Hub LLM.exe。',
    '3. 识别模型训练入口使用 pc\\NeuroLab Hub Vision.exe。',
    '4. 树莓派端将 pi 目录复制到设备后，执行 pi/start_pi_node.sh start。',
    '5. 首次运行时先执行软件自检，按需自动安装依赖。',
    '',
    '目录说明：',
    '- pc\\APP 为隐藏运行时目录，请勿删除。',
    '- pi\\APP 为树莓派运行时目录。',
    '- 如需安装到 Windows，请使用 NeuroLab-Hub-Setup-v*.exe。'
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
  Write-Host 'Main executable:' -ForegroundColor Green
  Write-Host $PcExePath -ForegroundColor Green
  Write-Host 'LLM executable:' -ForegroundColor Green
  Write-Host $PcLlmExePath -ForegroundColor Green
  Write-Host 'Vision executable:' -ForegroundColor Green
  Write-Host $PcVisionExePath -ForegroundColor Green
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