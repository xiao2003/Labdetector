# 系统环境问题与手动修复指南

适用目录：`D:\Labdetector`  
整理日期：2026 年 3 月 8 日

## 1. 说明

这份文档汇总了我在当前机器和当前项目里实际遇到的系统层面问题。重点不是项目代码本身，而是 Windows、Python、PowerShell、Git 和打包工具环境导致的异常。你按下面的步骤手动修完后，我再继续做联调测试。

## 2. 已遇到的系统层面问题总表

### 2.1 `python` 命令不可用

实际现象：

- 直接执行 `python xxx.py` 时，PowerShell 报错：`python.exe 无法运行: 系统无法访问此文件`
- 这不是脚本语法错误，而是系统没有把 `python` 命令指到真实解释器

当前机器可用解释器路径：

- `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`

高概率原因：

- Windows 的 `App Execution Aliases` 把 `python.exe` 指向了 `WindowsApps` 占位程序
- PATH 里 `WindowsApps` 在真实 Python 之前
- Python 安装不完整，只有占位符，没有真实可执行文件映射

### 2.2 `py` 启动器不可用

实际现象：

- 执行 `py -3.11` 报错：`No installed Python found!`

高概率原因：

- Python Launcher 没有安装
- Python Launcher 注册损坏
- 当前 Python 安装未正确写入注册表

### 2.3 双击 `.ps1` 脚本会闪退

实际现象：

- 双击 `build_desktop_exe.ps1`、`build_installer.ps1` 之类脚本时窗口一闪而过
- 早期还出现过中文注释在 Windows PowerShell 5.1 中显示异常的问题

高概率原因：

- 直接双击 `.ps1` 默认不会保留终端窗口
- PowerShell 执行策略拦截
- Windows PowerShell 5.1 对 UTF-8 无 BOM 文件兼容性差

### 2.4 Git 远端认证异常

实际现象：

- 查询远端标签时出现：`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`

高概率原因：

- Git Credential Manager 没登录
- GitHub HTTPS 凭据失效
- 当前终端会话拿不到系统凭据

### 2.5 Inno Setup 未安装时无法生成安装包

实际现象：

- 运行安装包构建脚本时找不到 `ISCC.exe`

高概率原因：

- 机器未安装 Inno Setup
- 已安装，但安装路径不在脚本默认搜索范围内

### 2.6 本地构建产物会反复污染仓库状态

实际现象：

- 每次构建后会出现新的 ZIP、EXE、临时目录、缓存目录

当前处理状态：

- 我已经把新版 EXE 和 ZIP 文件名加入 `.gitignore`
- 后续本地构建后，仓库不应再因为 `NeuroLab-Hub-*.zip`、`pc/NeuroLab Hub*.exe` 变脏

## 3. 手动修复办法

### 3.1 修复 `python` 命令

#### 方案 A：关闭 Windows 的 Python 占位别名

1. 打开 `设置`。
2. 进入 `应用`。
3. 进入 `高级应用设置`。
4. 打开 `应用执行别名`。
5. 找到：
   - `python.exe`
   - `python3.exe`
6. 将这两个别名关闭。

#### 方案 B：修正 PATH 顺序

把以下两个路径加入系统 PATH，并放在 `WindowsApps` 前面：

- `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\`
- `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\Scripts\`

建议检查命令：

```powershell
where python
where pip
```

期望结果：

- 第一条 `python` 路径应指向 `Python311\python.exe`
- 不能再优先指向 `C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\python.exe`

#### 方案 C：重新安装 Python 3.11

如果上面两步无效，直接重装 Python 3.11，安装时务必勾选：

- `Add python.exe to PATH`
- `Install launcher for all users`

安装完成后重开终端，再检查：

```powershell
python --version
pip --version
where python
```

### 3.2 修复 `py` 启动器

如果 `python` 能用但 `py` 仍不能用，通常说明 Launcher 有问题。

处理方法：

1. 重新运行 Python 安装器。
2. 选择 `Modify` 或直接重装。
3. 勾选 `Python Launcher`。
4. 安装完成后重新开终端。

检查命令：

```powershell
py --list-paths
py -3.11 --version
```

### 3.3 修复 `.ps1` 双击闪退

最稳妥的做法不是双击，而是在终端里运行：

```powershell
powershell -NoExit -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_desktop_exe.ps1
powershell -NoExit -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_portable_zip.ps1
powershell -NoExit -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_installer.ps1
```

如果你希望双击也能看到结果，优先双击这些 `.cmd` 包装器：

- `scripts\build_desktop_exe.cmd`
- `scripts\build_portable_zip.cmd`
- `scripts\build_installer.cmd`

如果 PowerShell 5.1 仍显示中文乱码，建议：

1. 安装 PowerShell 7 (`pwsh`)
2. 用 `pwsh` 执行打包脚本
3. 或继续使用仓库里现有的 `.cmd` 包装器

### 3.4 修复 Git HTTPS 凭据问题

先执行：

```powershell
git config --global credential.helper manager-core
```

然后重新登录 GitHub。常见做法：

1. 安装或修复 Git for Windows
2. 确认 Git Credential Manager 已启用
3. 第一次 `git fetch` / `git push` 时重新认证

如果你装了 GitHub CLI，也可以先登录：

```powershell
gh auth login
```

### 3.5 修复 Inno Setup 缺失问题

方法一：手动下载安装 Inno Setup 6

- 官网：[https://jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php)

方法二：如果机器装了 Chocolatey：

```powershell
choco install innosetup -y
```

安装完成后检查：

```powershell
Test-Path 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

### 3.6 推荐你完成后的最小自检命令

请你手动修完后，在终端执行下面这组命令：

```powershell
python --version
pip --version
where python
where pip
py --list-paths
powershell -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_desktop_exe.ps1 -NoPause
powershell -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_installer.ps1 -SkipDesktopBuild -NoPause
```

## 4. 你修完后发给我的内容

你修完后，把下面这些输出贴给我，我就继续测试：

1. `python --version`
2. `where python`
3. `py --list-paths`
4. `powershell -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_desktop_exe.ps1 -NoPause` 的最后 20 行输出
5. `powershell -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_installer.ps1 -SkipDesktopBuild -NoPause` 的最后 20 行输出

## 5. 我修完环境后会继续做什么

你把环境问题处理完之后，我会继续做这几项复测：

1. `python` / `py` 命令链复测
2. PC 主程序、LLM 工作台、Vision 工作台烟测
3. Pi CLI 参数与自检复测
4. 完整桌面包、便携包、安装包重建复测
5. 如你需要，再继续核对 GitHub Release 资产
