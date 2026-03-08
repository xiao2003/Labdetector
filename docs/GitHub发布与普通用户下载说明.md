# GitHub 发布与普通用户下载说明

## 1. 页面分工

建议将 GitHub 仓库分成三层用途：

- 仓库首页：给开发者，展示源码、文档、接口和训练说明。
- Releases 页面：给普通用户，下载安装器或完整 ZIP。
- 安装后的本地目录：Windows 用户看到 `LabDetector.exe / Lab.exe + APP`，树莓派用户看到 `start_pi_node.sh + APP`。

## 2. 实施方式

### 2.1 仓库首页

在 `README.md` 中明确写清：

- 开发者请 `git clone` 源码仓库。
- 普通用户不要下载源码压缩包，直接进入 Releases 页面。

### 2.2 Releases 页面

当前仓库已提供 GitHub Actions 工作流：

- 文件：`.github/workflows/release-desktop.yml`
- 触发方式：推送形如 `v3.0.4` 的标签
- 产物：
  - `LabDetector-Setup-vX.Y.Z.exe`
  - `LabDetector-vX.Y.Z.zip`
  - `LabDetector-Portable-vX.Y.Z.zip`

普通用户建议按场景下载：

- Windows 安装版：`LabDetector-Setup-vX.Y.Z.exe`
- PC + Pi 完整交付包：`LabDetector-vX.Y.Z.zip`
- 便携解压版：`LabDetector-Portable-vX.Y.Z.zip`

### 2.3 安装后的电脑

安装器会将软件安装为：

```text
安装目录
├─ LabDetector.exe
├─ Lab.exe
├─ LabDetectorTraining.exe
├─ LabTraining.exe
└─ APP
```

其中：

- `LabDetector.exe` 是用户启动入口
- `APP` 是隐藏运行时目录

## 3. 发布流程

1. 开发者完成代码修改并推送到 `master`
2. 更新 `VERSION`
3. 打标签，例如 `v3.0.4`
4. 推送标签：

```powershell
git tag v3.0.4
git push origin v3.0.4
```

5. GitHub Actions 自动构建并创建 Release
6. 普通用户进入 Releases 页面下载安装器

## 4. 建议

- 仓库首页不要把源码 zip 当成普通用户下载入口
- Release 描述中明确标注“普通用户下载安装器，开发者使用源码仓库”
- 如果后续要更像正式软件，可继续补代码签名和自动更新

## 5. GitHub Releases 上传清单

以下清单适用于当前 `v3.0.4` 发布物，上传时建议保持文件名不变。

### 5.1 建议上传顺序

1. `LabDetector-Setup-v3.0.4.exe`
2. `LabDetector-v3.0.4.zip`
3. `LabDetector-Portable-v3.0.4.zip`

### 5.2 文件清单

#### A. Windows 安装版

- 文件名：`LabDetector-Setup-v3.0.4.exe`
- 当前路径：`D:\Labdetector\LabDetector-Setup-v3.0.4.exe`
- 当前大小：约 `266.03 MB`
- 面向用户：普通 Windows 用户
- Release 显示名建议：`LabDetector 3.0.4 Windows 安装版`
- Release 说明建议：
  - 双击进入安装向导
  - 支持自定义安装目录
  - 安装后桌面或开始菜单可直接启动 `LabDetector.exe / Lab.exe / LabTraining.exe`

#### B. PC + Pi 完整发布包

- 文件名：`LabDetector-v3.0.4.zip`
- 当前路径：`D:\Labdetector\LabDetector-v3.0.4.zip`
- 当前大小：约 `315.93 MB`
- 面向用户：需要同时部署 PC 端和 Pi 端的用户
- Release 显示名建议：`LabDetector 3.0.4 PC+Pi 完整包`
- Release 说明建议：
  - 解压后包含 `pc/` 与 `pi/` 两端目录
  - PC 端运行 `pc/Lab.exe`
  - Pi 端运行 `pi/start_pi_node.sh`
  - 适合实验室闭环部署、树莓派联调和交付备份

#### C. 便携解压版

- 文件名：`LabDetector-Portable-v3.0.4.zip`
- 当前路径：`D:\Labdetector\LabDetector-Portable-v3.0.4.zip`
- 当前大小：约 `315.85 MB`
- 面向用户：不想安装、希望解压即用的用户
- Release 显示名建议：`LabDetector 3.0.4 便携版`
- Release 说明建议：
  - 无需安装，解压即可运行
  - PC 端运行 `pc/Lab.exe`
  - 训练入口为 `pc/LabTraining.exe`
  - Pi 端运行 `pi/start_pi_node.sh`

### 5.3 上传前核对项

- `LabDetector-Setup-v3.0.4.exe` 可正常启动安装向导
- `LabDetector-v3.0.4.zip` 解压后包含 `pc/`、`pi/`、`README_QUICKSTART.txt`
- `LabDetector-Portable-v3.0.4.zip` 解压后包含 `pc/`、`pi/`、`README_PORTABLE.txt`
- `pc/` 内存在 `Lab.exe`、`LabTraining.exe`、`APP/`
- `pi/` 内存在 `start_pi_node.sh`、`APP/`
- `pc/APP/` 内存在 `python_runtime/` 与 `training_runtime/`

### 5.4 Release 页面建议文案

可直接放在 GitHub Release 描述里：

```text
LabDetector 3.0.4 发布说明

给开发者：
- 请使用源码仓库进行调试、训练与二次开发

给普通用户：
- 优先下载 LabDetector-Setup-v3.0.4.exe
- 如果不想安装，可下载 LabDetector-Portable-v3.0.4.zip
- 如果需要同时部署 PC 端与 Pi 端，请下载 LabDetector-v3.0.4.zip

启动方式：
- Windows 主程序：pc/Lab.exe 或安装后的 LabDetector.exe
- Windows 训练工作台：pc/LabTraining.exe
- Raspberry Pi：pi/start_pi_node.sh start --auto-install-deps

本版本重点：
- PC/Pi 双端闭环可视化
- 打包后训练运行时内置
- 缺失依赖支持自检自动安装
- 新增 LM Studio / vLLM / SGLang / LMDeploy / Xinference / llama.cpp 本地模型服务接入
```

### 5.5 GitHub 操作顺序

1. 进入仓库 `Releases`
2. 点击 `Draft a new release`
3. 选择标签 `v3.0.4`
4. 标题建议填写：`LabDetector 3.0.4`
5. 粘贴上面的 Release 说明文案
6. 依次上传三个文件
7. 检查文件名与大小是否正确
8. 点击 `Publish release`