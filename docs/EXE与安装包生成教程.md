# NeuroLab Hub：可编排专家模型的实验室多模态智能中枢 EXE 与安装包生成教程

## 1. 目标产物

- `pc/NeuroLab Hub.exe`
- `pc/NeuroLab Hub LLM.exe`
- `NeuroLab-Hub-v<版本号>.zip`
- `NeuroLab-Hub-Portable-v<版本号>.zip`
- `NeuroLab-Hub-Setup-v<版本号>.exe`

## 2. 生成命令

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_desktop_exe.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_portable_zip.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

