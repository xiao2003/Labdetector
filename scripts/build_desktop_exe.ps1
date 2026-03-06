param(
  [string]$PythonExe = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -Path (Join-Path $ProjectRoot 'VERSION') -Raw).Trim()
$WorkRoot = Join-Path $ProjectRoot '.pyi_work'
$DistRoot = Join-Path $ProjectRoot '.pyi_dist'
$ReleaseRoot = Join-Path $ProjectRoot ("release\LabDetector-v$Version")
$ZipPath = Join-Path $ProjectRoot ("release\LabDetector-v$Version.zip")
$StageFolder = Join-Path $DistRoot 'LabDetector'

if (!(Test-Path $PythonExe)) {
  throw "Python 解释器不存在: $PythonExe"
}

& $PythonExe (Join-Path $ProjectRoot 'scripts\generate_brand_assets.py')
& $PythonExe (Join-Path $ProjectRoot 'scripts\write_version_info.py')
& $PythonExe -m pip show pyinstaller | Out-Null
if ($LASTEXITCODE -ne 0) {
  & $PythonExe -m pip install pyinstaller
}

if (Test-Path $WorkRoot) {
  Remove-Item -Recurse -Force $WorkRoot
}
if (Test-Path $DistRoot) {
  Remove-Item -Recurse -Force $DistRoot
}
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null

Push-Location $ProjectRoot
try {
  & $PythonExe -m PyInstaller --noconfirm --clean --workpath $WorkRoot --distpath $DistRoot labdetector.spec
}
finally {
  Pop-Location
}

if (!(Test-Path $StageFolder)) {
  throw "构建失败，未找到输出目录: $StageFolder"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReleaseRoot) | Out-Null
if (Test-Path $ReleaseRoot) {
  Remove-Item -Recurse -Force $ReleaseRoot
}
Copy-Item -Path $StageFolder -Destination $ReleaseRoot -Recurse -Force

$InternalPath = Join-Path $ReleaseRoot '_internal'
if (Test-Path $InternalPath) {
  attrib +h +s $InternalPath | Out-Null
}

if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Compress-Archive -Path $ReleaseRoot -DestinationPath $ZipPath -Force

$LegacyArtifacts = @(
  $WorkRoot,
  $DistRoot,
  (Join-Path $ProjectRoot 'build'),
  (Join-Path $ProjectRoot 'dist')
)
foreach ($artifact in $LegacyArtifacts) {
  if (Test-Path $artifact) {
    Remove-Item -Recurse -Force $artifact
  }
}

Write-Host ''
Write-Host '正式发布目录:' -ForegroundColor Green
Write-Host $ReleaseRoot -ForegroundColor Green
Write-Host '正式运行入口:' -ForegroundColor Green
Write-Host (Join-Path $ReleaseRoot 'LabDetector.exe') -ForegroundColor Green
Write-Host '发布压缩包:' -ForegroundColor Green
Write-Host $ZipPath -ForegroundColor Green
