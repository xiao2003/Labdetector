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
    if ($item.Name -in @('__pycache__', 'APP', 'log', 'training_runs', '.idea')) {
      continue
    }
    Copy-Item -Path $item.FullName -Destination (Join-Path $DestinationDir $item.Name) -Recurse -Force
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
  $PcAppRoot = Join-Path $PcRoot 'APP'
  $PcPythonRuntimeRoot = Join-Path $PcAppRoot 'python_runtime'
  $PcTrainingRuntimeRoot = Join-Path $PcAppRoot 'training_runtime'
  $PiAppRoot = Join-Path $PiRoot 'APP'
  $ZipPath = Join-Path $ProjectRoot ("NeuroLab-Hub-v$Version.zip")
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
  $PythonHome = Split-Path -Parent $PythonExe

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

  foreach ($artifact in @($PcExePath, $PcLlmExePath, $PcVisionExePath, $PcAppRoot, $PiAppRoot, $BundleRoot, $ZipPath)) {
    if (Test-Path $artifact) {
      Remove-Item -Recurse -Force $artifact
    }
  }

  Copy-Item -Path $StageExePath -Destination $PcExePath -Force
  Copy-Item -Path $PcExePath -Destination $PcLlmExePath -Force
  Copy-Item -Path $PcExePath -Destination $PcVisionExePath -Force

  New-Item -ItemType Directory -Force -Path $PcAppRoot | Out-Null
  foreach ($file in @('launcher.py', 'config.ini', 'project_identity.json', 'VERSION')) {
    Copy-Item -Path (Join-Path $ProjectRoot $file) -Destination (Join-Path $PcAppRoot $file) -Force
  }
  foreach ($folder in @('assets', 'docs', 'test')) {
    $sourceFolder = Join-Path $ProjectRoot $folder
    if (Test-Path $sourceFolder) {
      Copy-Item -Path $sourceFolder -Destination (Join-Path $PcAppRoot $folder) -Recurse -Force
    }
  }
  Copy-SourceTree -SourceDir $PcRoot -DestinationDir (Join-Path $PcAppRoot 'pc')
  Copy-SourceTree -SourceDir $PiRoot -DestinationDir (Join-Path $PcAppRoot 'pi')

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
    'voice',
    'testing'
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
    '1. Run pc\NeuroLab Hub.exe as the main desktop entry.',
    '2. Run pc\NeuroLab Hub LLM.exe for the LLM training entry.',
    '3. Run pc\NeuroLab Hub Vision.exe for the vision training entry.',
    '4. Copy the pi folder to the Raspberry Pi and run pi/start_pi_node.sh start.',
    '5. On first launch, the self-check stage downloads and installs required dependencies automatically.',
    '',
    'Directories:',
    '- pc\APP is the desktop runtime folder.',
    '- pi\APP is the Raspberry Pi runtime folder.',
    '- test contains PC/Pi test scripts and the testing manual.'
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
