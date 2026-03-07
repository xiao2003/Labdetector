param(
  [string]$InnoCompilerPath = "",
  [switch]$SkipDesktopBuild,
  [string]$PythonExe = "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -Path (Join-Path $ProjectRoot "VERSION") -Raw).Trim()
$ReleaseRoot = Join-Path $ProjectRoot "pc"
$DesktopExe = Join-Path $ReleaseRoot "LabDetector.exe"
$InstallerScript = Join-Path $ProjectRoot "installer\LabDetector.iss"
$InstallerOutput = Join-Path $ProjectRoot ("LabDetector-Setup-v$Version.exe")

if (!(Test-Path $InstallerScript)) {
  throw "Installer script not found: $InstallerScript"
}

if (!(Test-Path $DesktopExe)) {
  if ($SkipDesktopBuild) {
    throw "Desktop EXE not found: $DesktopExe"
  }
  & (Join-Path $PSHOME 'powershell.exe') -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot 'scripts\build_desktop_exe.ps1') -PythonExe $PythonExe
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
