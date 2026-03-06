param(
  [string]$InnoCompilerPath = "",
  [switch]$SkipDesktopBuild,
  [string]$PythonExe = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python311\\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -Path (Join-Path $ProjectRoot "VERSION") -Raw).Trim()
$ReleaseRoot = Join-Path $ProjectRoot ("release\LabDetector-v$Version")
$DesktopExe = Join-Path $ReleaseRoot "LabDetector.exe"
$InstallerScript = Join-Path $ProjectRoot "installer\LabDetector.iss"
$InstallerOutput = Join-Path $ProjectRoot ("release\LabDetector-Setup-v$Version.exe")

if (!(Test-Path $InstallerScript)) {
  throw "未找到安装器脚本: $InstallerScript"
}

if (!(Test-Path $DesktopExe)) {
  if ($SkipDesktopBuild) {
    throw "未找到正式桌面版 EXE: $DesktopExe"
  }
  & (Join-Path $PSHOME 'powershell.exe') -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\build_desktop_exe.ps1') -PythonExe $PythonExe
}

if (!(Test-Path $ReleaseRoot)) {
  throw "未找到正式发布目录: $ReleaseRoot"
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
  throw "未找到 Inno Setup 编译器 ISCC.exe。请先安装官方 Inno Setup 6.x，或使用 -InnoCompilerPath 指定路径。官方下载页: https://jrsoftware.org/isdl.php"
}

Push-Location $ProjectRoot
try {
  & $InnoCompilerPath "/DMyAppVersion=$Version" "/DReleaseDir=$ReleaseRoot" $InstallerScript
}
finally {
  Pop-Location
}

if (!(Test-Path $InstallerOutput)) {
  throw "安装器构建失败，未找到输出文件: $InstallerOutput"
}

Write-Host ''
Write-Host '安装器输出:' -ForegroundColor Green
Write-Host $InstallerOutput -ForegroundColor Green
Write-Host '安装源目录:' -ForegroundColor Green
Write-Host $ReleaseRoot -ForegroundColor Green
