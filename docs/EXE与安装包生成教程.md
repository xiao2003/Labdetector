# EXE 与引导式安装包生成教程

本文说明如何从 `D:\Labdetector` 源码仓库生成：

- PC 端可执行文件 `pc/LabDetector.exe` / `pc/Lab.exe`
- PC 端训练入口 `pc/LabDetectorTraining.exe` / `pc/LabTraining.exe`
- Pi 端运行目录 `pi/APP`
- 压缩发布包 `LabDetector-v<版本号>.zip` 与 `LabDetector-Portable-v<版本号>.zip`
- Windows 引导式安装包 `LabDetector-Setup-v<版本号>.exe`

## 1. 目标产物

构建完成后，仓库根目录会得到以下正式产物：

```text
D:\Labdetector
├─ pc\LabDetector.exe
├─ pc\Lab.exe
├─ pc\LabDetectorTraining.exe
├─ pc\LabTraining.exe
├─ pc\APP\...
├─ pi\start_pi_node.sh
├─ pi\APP\...
├─ LabDetector-v<版本号>.zip
├─ LabDetector-Portable-v<版本号>.zip
└─ LabDetector-Setup-v<版本号>.exe
```

说明：

- `pc/LabDetector.exe` 是 Windows 桌面主程序。
- `pc/APP` 是桌面程序运行时目录，由 PyInstaller 生成并被主程序依赖。
- `pi/start_pi_node.sh` 是树莓派侧启动入口。
- `pi/APP` 是 Pi 侧运行时目录和脚本集合。
- `LabDetector-Setup-v<版本号>.exe` 是 Inno Setup 生成的引导式安装包。

## 2. 前置条件

建议环境：

- Windows 10 / 11
- Python 3.11
- PowerShell 5.1 或更高
- Git
- 可选：Inno Setup 6.x

必须保证：

- 当前工作目录为 `D:\Labdetector`
- `VERSION` 文件中的版本号已更新
- `assets/branding/labdetector.ico` 等品牌资源已存在

## 3. 关键脚本说明

### 3.1 桌面 EXE 构建脚本

文件：`scripts/build_desktop_exe.ps1`

职责：

1. 生成品牌资源和版本资源
2. 执行默认配置引导
3. 检查并安装 `pyinstaller`
4. 调用 `labdetector.spec` 生成 PyInstaller 目录版程序
5. 将产物整理到 `pc/` 和 `pi/`
6. 生成 `Lab.exe`、`LabTraining.exe` 等短名启动器
7. 在 `pc/APP` 内补齐 `python_runtime` 与 `training_runtime`
8. 生成发布压缩包 `LabDetector-v<版本号>.zip`
9. 清理 `.pyi_work`、`.pyi_dist`、`build`、`dist`、`release` 等临时目录

### 3.2 安装包构建脚本

文件：`scripts/build_installer.ps1`

职责：

1. 检查 `pc/LabDetector.exe` 是否已存在
2. 必要时自动调用 `build_desktop_exe.ps1`
3. 调用 `installer/LabDetector.iss`
4. 输出 `LabDetector-Setup-v<版本号>.exe`

### 3.3 发布检查脚本链

- `scripts/prepare_release_bundle.ps1`：检查并汇总当前发布产物
- `scripts/install_inno_setup.ps1`：自动下载和安装 Inno Setup
- `scripts/write_version_info.py`：生成 Windows 版本资源
- `labdetector.spec`：PyInstaller 打包规格文件

## 4. 生成桌面 EXE

在 PowerShell 中执行：

```powershell
Set-Location D:\Labdetector
powershell -ExecutionPolicy Bypass -File .\scripts\build_desktop_exe.ps1
```

如需指定 Python：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_desktop_exe.ps1 -PythonExe "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
```

成功后重点检查：

- `pc/LabDetector.exe` / `pc/Lab.exe`
- `pc/LabDetectorTraining.exe` / `pc/LabTraining.exe`
- `pc/APP/`
- `pi/start_pi_node.sh`
- `pi/APP/`
- `LabDetector-v<版本号>.zip`

## 5. 生成引导式安装包

### 5.1 安装 Inno Setup

如果本机尚未安装 Inno Setup，可执行：

```powershell
Set-Location D:\Labdetector
powershell -ExecutionPolicy Bypass -File .\scripts\install_inno_setup.ps1
```

### 5.2 构建安装包

```powershell
Set-Location D:\Labdetector
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

如已确认桌面 EXE 已构建好，可跳过桌面重打：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -SkipDesktopBuild
```

如需手动指定 Inno 编译器路径：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -InnoCompilerPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

成功后产物为：

```text
D:\Labdetector\LabDetector-Setup-v<版本号>.exe
```

## 6. 安装包工作原理

安装脚本文件：`installer/LabDetector.iss`

当前安装行为：

- 默认安装目录：`{autopf}\LabDetector`
- 允许用户自定义安装路径
- 安装时展示许可协议与安装前说明
- 安装主程序 `LabDetector.exe`
- 安装隐藏运行时目录 `APP`
- 创建开始菜单快捷方式
- 可选创建桌面快捷方式
- 安装完成后可直接启动软件

## 7. 常见构建顺序

推荐完整构建顺序：

1. 更新 `VERSION`
2. 提交源码变更
3. 执行桌面 EXE 构建
4. 验证 `pc/LabDetector.exe`
5. 执行安装包构建
6. 验证 `LabDetector-Setup-v<版本号>.exe`
7. 推送 GitHub

## 8. 构建后检查清单

至少检查以下内容：

- `pc/LabDetector.exe` 存在且能启动
- `pc/APP` 存在
- `pi/start_pi_node.sh` 存在
- `pi/APP` 存在
- `LabDetector-v<版本号>.zip` 已生成
- `LabDetector-Setup-v<版本号>.exe` 已生成
- 安装向导中的图标、软件名、公司名、版本号正确
- 安装后的默认启动入口正确

## 9. 常见问题

### 9.1 缺少 `pyinstaller`

`build_desktop_exe.ps1` 会自动检测并尝试安装。

### 9.2 找不到 `ISCC.exe`

说明 Inno Setup 未安装，或路径不在默认位置。可先执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_inno_setup.ps1
```

### 9.3 打包后目录里为什么还有 `APP`

这是目录版桌面软件的运行时目录，不是冗余文件。`LabDetector.exe` 依赖其中的 Python 运行时、资源和业务文件。

### 9.4 如何只更新安装包，不重打 EXE

如果 `pc/LabDetector.exe` 已是最新，可使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -SkipDesktopBuild
```

## 10. 推荐发布命令

如果要完成一轮标准发布，可按下面顺序执行：

```powershell
Set-Location D:\Labdetector
powershell -ExecutionPolicy Bypass -File .\scripts\build_desktop_exe.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

然后确认：

- `pc/LabDetector.exe`
- `LabDetector-v<版本号>.zip`
- `LabDetector-Setup-v<版本号>.exe`

这三项都存在后，再提交并推送 GitHub。
