# NeuroLab Hub——可编排专家模型的实验室多模态智能中枢 EXE 与安装包生成教程

## 1. 目标产物

- `release/NeuroLab_Hub_<版本号>_<标签>.zip`
- `NeuroLab-Hub-Setup-v<版本号>.exe`
- `stage_<标签>/NeuroLab Hub SilentDir/`

## 2. 生成命令

```powershell
python .\installer\build_release_package.py --version 1.0.0
```

说明：

1. 当前发布链以 `SilentDir/onedir` 为正式交付基线。
2. `build_release_package.py` 会同时生成：
   - 便携压缩包
   - 安装界面对应的 `Setup.exe`
3. 若本机未安装 Inno Setup 6，脚本会直接报错并停止，避免再次产出“只有便携包、没有安装界面”的不完整发布物。
