# NeuroLab Hub EXE 与安装包生成教程

## 1. 目标产物

- `pc/Lab.exe`
- `pc/LabTraining.exe`
- `LabDetector-v<版本号>.zip`
- `LabDetector-Portable-v<版本号>.zip`
- `LabDetector-Setup-v<版本号>.exe`

## 2. 生成命令

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_desktop_exe.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_portable_zip.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```
