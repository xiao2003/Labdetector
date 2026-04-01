param(
  [string]$PythonExe = 'C:\Users\yuhua\AppData\Local\Programs\Python\Python311\python.exe',
  [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot 'tmp\build_logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("build_desktop_exe_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$TranscriptStarted = $false
$CanPause = (-not $NoPause) -and ($Host.Name -eq 'ConsoleHost') -and [string]::IsNullOrEmpty($env:CI) -and [string]::IsNullOrEmpty($env:GITHUB_ACTIONS)

function Copy-SourceTree {
  param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$DestinationDir
  )

  if (!(Test-Path $SourceDir)) {
    throw "Source tree not found: $SourceDir"
  }

  New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
  foreach ($item in Get-ChildItem -LiteralPath $SourceDir -Force) {
    if ($item.Name -in @('__pycache__', 'APP', 'log', 'training_runs', 'training_assets', '.idea')) {
      continue
    }
    if ($SourceDir -eq $PcRoot -and $item.Name -like 'NeuroLab Hub*.exe') {
      continue
    }
    if ($SourceDir -like '*\pc\voice' -and $item.Name -in @('model', 'models')) {
      continue
    }
    Copy-Item -Path $item.FullName -Destination (Join-Path $DestinationDir $item.Name) -Recurse -Force
  }
}

function Copy-BundledVoskAssets {
  param(
    [Parameter(Mandatory = $true)][string]$ProjectRootDir,
    [Parameter(Mandatory = $true)][string]$BundleRootDir
  )

  $source = Join-Path $ProjectRootDir 'runtime_data\speech_assetsosk-model-small-cn-0.22'
  if (!(Test-Path (Join-Path $source 'aminal.mdl'))) {
    throw "Bundled Vosk assets not found: $source"
  }
  $target = Join-Path $BundleRootDir 'APPuntime_data\speech_assetsosk-model-small-cn-0.22'
  if (Test-Path $target) {
    Remove-Item -Recurse -Force $target
  }
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object { $_.Name -notlike '*.zip' } | ForEach-Object {
    $relative = $_.FullName.Substring($source.Length).TrimStart('\')
    $destination = Join-Path $target $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -Path $_.FullName -Destination $destination -Force
  }
}

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
  $ZipPath = Join-Path $ProjectRoot ("NeuroLab-Hub-v$Version.zip")
  $SourceZipPath = Join-Path $ProjectRoot ("NeuroLab-Hub-source-v$Version.zip")
  $StageExePath = Join-Path $DistRoot 'NeuroLab Hub.exe'

  if (!(Test-Path $PythonExe)) {
    $resolvedPython = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if ($resolvedPython -and $resolvedPython.Source) {
      $PythonExe = $resolvedPython.Source
    }
  }
  if (!(Test-Path $PythonExe)) {
    throw "Python interpreter not found: $PythonExe"
  }

  & $PythonExe (Join-Path $ProjectRoot 'scripts\generate_brand_assets.py')
  if ($LASTEXITCODE -ne 0) {
    throw 'Brand asset generation failed.'
  }

  & $PythonExe (Join-Path $ProjectRoot 'scripts\write_version_info.py')
  if ($LASTEXITCODE -ne 0) {
    throw 'Version resource generation failed.'
  }

  & $PythonExe (Join-Path $ProjectRoot 'scripts\check_source_encoding.py')
  if ($LASTEXITCODE -ne 0) {
    throw 'Source encoding check failed.'
  }

  foreach ($path in @($WorkRoot, $DistRoot, $BundleStageRoot)) {
    if (Test-Path $path) {
      Remove-Item -Recurse -Force $path
    }
    New-Item -ItemType Directory -Force -Path $path | Out-Null
  }

  Push-Location $ProjectRoot
  try {
    $env:NEUROLAB_EXE_NAME = 'NeuroLab Hub'
    & $PythonExe -m pip show pyinstaller | Out-Null
    if ($LASTEXITCODE -ne 0) {
      & $PythonExe -m pip install pyinstaller
    }
    & $PythonExe -m PyInstaller --noconfirm --clean --workpath $WorkRoot --distpath $DistRoot neurolab_bootstrap.spec
    if ($LASTEXITCODE -ne 0) {
      throw 'PyInstaller bootstrap build failed.'
    }
  }
  finally {
    Remove-Item Env:NEUROLAB_EXE_NAME -ErrorAction SilentlyContinue
    Pop-Location
  }

  if (!(Test-Path $StageExePath)) {
    throw "Build output not found: $StageExePath"
  }

  foreach ($artifact in @($PcExePath, $PcLlmExePath, $PcVisionExePath, $BundleRoot, $ZipPath, $SourceZipPath)) {
    if (Test-Path $artifact) {
      Remove-Item -Recurse -Force $artifact
    }
  }

  Copy-Item -Path $StageExePath -Destination $PcExePath -Force
  Copy-Item -Path $PcExePath -Destination $PcLlmExePath -Force
  Copy-Item -Path $PcExePath -Destination $PcVisionExePath -Force

  New-Item -ItemType Directory -Force -Path $BundleRoot | Out-Null
  foreach ($launcher in @('NeuroLab Hub.exe', 'NeuroLab Hub LLM.exe', 'NeuroLab Hub Vision.exe')) {
    $source = Join-Path $PcRoot $launcher
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $BundleRoot $launcher) -Force
    }
  }

  foreach ($file in @('launcher.py', 'bootstrap_entry.py', 'project_identity.json', 'VERSION', 'README.md')) {
    $source = Join-Path $ProjectRoot $file
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $BundleRoot $file) -Force
    }
  }

  foreach ($folder in @('assets', 'docs', 'installer')) {
    $sourceFolder = Join-Path $ProjectRoot $folder
    if (Test-Path $sourceFolder) {
      Copy-Item -Path $sourceFolder -Destination (Join-Path $BundleRoot $folder) -Recurse -Force
    }
  }

  Copy-SourceTree -SourceDir $PcRoot -DestinationDir (Join-Path $BundleRoot 'pc')
  Copy-SourceTree -SourceDir $PiRoot -DestinationDir (Join-Path $BundleRoot 'pi')
  Copy-BundledVoskAssets -ProjectRootDir $ProjectRoot -BundleRootDir $BundleRoot

  $quickStartLines = @(
    'NeuroLab Hub Quick Start',
    '========================',
    '1. 运行根目录中的 NeuroLab Hub.exe 进入主界面。',
    '2. 首次启动时，入口会检查 Python 和核心 GUI 依赖。',
    '3. 进入软件后执行系统自检；Vosk 离线语音模型与固定管家层模型已内置，其余缺失依赖会自动补齐。',
    '4. 若使用 Ollama，本地模型会在首次选择时自动拉取。',
    '5. 如需 Pi 节点，请将 pi 目录复制到 Raspberry Pi 后执行 pi/start_pi_node.sh。',
    '',
    '说明：',
    '- 交付包已内置 Vosk 离线语音模型与固定管家层小模型。',
    '- 交付包不再内置完整 Python 运行时。',
    '- 执行层 Ollama / Qwen 等外部后端模型不随包分发，按需在本机后端环境获取。'
  )
  Set-Content -Path (Join-Path $BundleRoot 'README_QUICKSTART.txt') -Value $quickStartLines -Encoding UTF8

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::CreateFromDirectory($BundleRoot, $ZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)

  $SourceStageRoot = Join-Path $BundleStageRoot 'NeuroLab Hub Source'
  New-Item -ItemType Directory -Force -Path $SourceStageRoot | Out-Null
  foreach ($file in @('.gitignore', 'README.md', 'LICENSE', 'requirements.txt', 'setup.py', 'launcher.py', 'bootstrap_entry.py', 'VERSION', 'project_identity.json', 'neurolab_bootstrap.spec', 'neurolab_hub.spec')) {
    $source = Join-Path $ProjectRoot $file
    if (Test-Path $source) {
      Copy-Item -Path $source -Destination (Join-Path $SourceStageRoot $file) -Force
    }
  }
  foreach ($folder in @('assets', 'docs', 'installer', 'scripts', 'test')) {
    $sourceFolder = Join-Path $ProjectRoot $folder
    if (Test-Path $sourceFolder) {
      Copy-Item -Path $sourceFolder -Destination (Join-Path $SourceStageRoot $folder) -Recurse -Force
    }
  }
  Copy-SourceTree -SourceDir $PcRoot -DestinationDir (Join-Path $SourceStageRoot 'pc')
  Copy-SourceTree -SourceDir $PiRoot -DestinationDir (Join-Path $SourceStageRoot 'pi')
  [System.IO.Compression.ZipFile]::CreateFromDirectory($SourceStageRoot, $SourceZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)

  foreach ($artifact in @($WorkRoot, $DistRoot, $BundleStageRoot, (Join-Path $ProjectRoot 'build'), (Join-Path $ProjectRoot 'dist'), (Join-Path $ProjectRoot 'release'))) {
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
  Write-Host 'User package:' -ForegroundColor Green
  Write-Host $ZipPath -ForegroundColor Green
  Write-Host 'Source package:' -ForegroundColor Green
  Write-Host $SourceZipPath -ForegroundColor Green
  Write-Host 'Build log:' -ForegroundColor Green
  Write-Host $LogFile -ForegroundColor Green
}
catch {
  Write-Host ''
  Write-Host "Desktop packaging failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Build log: $LogFile" -ForegroundColor Yellow
  if ($CanPause) {
    Read-Host 'Press Enter to exit'
  }
  exit 1
}
finally {
  if ($TranscriptStarted) {
    Stop-Transcript | Out-Null
  }
}
