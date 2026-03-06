param(
  [string]$Version = "6.7.1",
  [string]$DownloadUrl = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_1/innosetup-6.7.1.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TmpDir = Join-Path $ProjectRoot 'tmp'
$InstallerPath = Join-Path $TmpDir ("innosetup-$Version.exe")
$candidates = @(
  'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
  'C:\Program Files\Inno Setup 6\ISCC.exe'
)

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
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
