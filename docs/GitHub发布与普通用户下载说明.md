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
- 触发方式：推送形如 `v3.0.2` 的标签
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
3. 打标签，例如 `v3.0.2`
4. 推送标签：

```powershell
git tag v3.0.2
git push origin v3.0.2
```

5. GitHub Actions 自动构建并创建 Release
6. 普通用户进入 Releases 页面下载安装器

## 4. 建议

- 仓库首页不要把源码 zip 当成普通用户下载入口
- Release 描述中明确标注“普通用户下载安装器，开发者使用源码仓库”
- 如果后续要更像正式软件，可继续补代码签名和自动更新
