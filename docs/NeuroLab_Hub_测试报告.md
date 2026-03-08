# NeuroLab Hub 测试报告

版本：3.0.6  
测试日期：2026 年 3 月 8 日  
测试目录：`D:\Labdetector`

## 一、测试目的

本次测试用于验证 NeuroLab Hub 当前版本在以下方面的可交付性：

1. 主程序和训练入口可正常启动
2. Pi CLI 命令层可正常解析
3. 核心 Python 入口文件无语法错误
4. Windows 桌面 EXE、便携 ZIP 和安装包可重新构建
5. 当前交付物与文档、版本号和命名保持一致

## 二、测试环境

### 2.1 软件环境

- Windows 10 64 位
- Python 3.11.9
- PyInstaller 6.19.0
- Inno Setup 6.7.1

### 2.2 测试说明

- 本轮测试在 `D:\Labdetector` 工作目录内完成。
- 当前环境中 `python` 和 `py` 命令未正确映射到实际 Python 安装，因此命令测试使用显式解释器路径 `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`。
- 该环境问题属于当前机器的 Python 启动器配置问题，不属于软件仓库功能缺陷。

## 三、执行记录

### 3.1 EXE 烟测

#### 主程序

- 命令：`Start-Process -FilePath 'D:\Labdetector\pc\NeuroLab Hub.exe' -ArgumentList '--smoke-test-file', 'D:\Labdetector\tmp\smoke_main.json' -Wait -PassThru`
- 结果：退出码 `0`
- 验证：生成 `tmp/smoke_main.json`

#### LLM 工作台

- 命令：`Start-Process -FilePath 'D:\Labdetector\pc\NeuroLab Hub LLM.exe' -ArgumentList '--smoke-test-file', 'D:\Labdetector\tmp\smoke_llm.json' -Wait -PassThru`
- 结果：退出码 `0`
- 验证：生成 `tmp/smoke_llm.json`

#### 识别模型工作台

- 命令：`Start-Process -FilePath 'D:\Labdetector\pc\NeuroLab Hub Vision.exe' -ArgumentList '--smoke-test-file', 'D:\Labdetector\tmp\smoke_vision.json' -Wait -PassThru`
- 结果：退出码 `0`
- 验证：生成 `tmp/smoke_vision.json`

### 3.2 Pi CLI 验证

#### 自检帮助

- 命令：`C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe pi\pi_cli.py self-check --help`
- 结果：通过
- 关键点：显示 `--auto-install-deps` 与 `--no-auto-install-deps`

#### 启动帮助

- 命令：`C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe pi\pi_cli.py start --help`
- 结果：通过
- 关键点：显示 `--pc-ip`、`--ws-port`、`--weights-path`、`--detector-conf` 等参数

### 3.3 核心 Python 文件编译验证

- 命令：`C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe -m py_compile ...`
- 覆盖文件：
  - `launcher.py`
  - `pc/app_identity.py`
  - `pc/core/subprocess_utils.py`
  - `pc/desktop_app.py`
  - `pc/webui/runtime.py`
  - `pc/core/ai_backend.py`
  - `pc/training/runtime_env.py`
  - `pc/training/train_manager.py`
  - `pc/main.py`
  - `pi/pi_cli.py`
  - `pi/pisend_receive.py`
- 结果：全部通过

### 3.4 打包链路验证

#### Windows 桌面 EXE 构建

- 命令：`powershell -ExecutionPolicy Bypass -File scripts/build_desktop_exe.ps1`
- 结果：通过
- 产物：
  - `pc/NeuroLab Hub.exe`
  - `pc/NeuroLab Hub LLM.exe`
  - `pc/NeuroLab Hub Vision.exe`
  - `NeuroLab-Hub-v3.0.6.zip`

#### 便携 ZIP 构建

- 命令：`powershell -ExecutionPolicy Bypass -File scripts/build_portable_zip.ps1`
- 结果：通过
- 产物：
  - `NeuroLab-Hub-Portable-v3.0.6.zip`
- 记录大小：约 `224.95 MB`

#### 安装包构建

- 命令：`powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1`
- 结果：通过
- 产物：
  - `NeuroLab-Hub-Setup-v3.0.6.exe`

## 四、测试结果汇总

| 编号 | 测试项 | 结果 | 说明 |
| --- | --- | --- | --- |
| T01 | 主程序启动烟测 | 通过 | 退出码 0，输出文件已生成 |
| T02 | LLM 工作台启动烟测 | 通过 | 退出码 0，输出文件已生成 |
| T03 | 识别模型工作台启动烟测 | 通过 | 退出码 0，输出文件已生成 |
| T04 | Pi CLI 自检帮助 | 通过 | 参数帮助正常显示 |
| T05 | Pi CLI 启动帮助 | 通过 | 参数帮助正常显示 |
| T06 | 核心 Python 文件编译 | 通过 | 无语法错误 |
| T07 | Windows 桌面 EXE 构建 | 通过 | 三个入口与完整包已生成 |
| T08 | 便携 ZIP 构建 | 通过 | 便携包已生成 |
| T09 | Windows 安装包构建 | 通过 | 安装包已生成 |

## 五、当前确认的产品状态

1. Windows 主程序和两个训练入口可独立启动。
2. 用户可通过安装版、完整包或便携版获得软件。
3. Pi 端自检和启动命令层可正常使用。
4. 打包链路可在当前环境下重建当前版本发布物。
5. 文档、安装器和交付物命名已统一为 `NeuroLab Hub`。

## 六、尚需现场联调的项目

以下项目依赖真实硬件、网络或实验数据，未在本轮本地测试中完全展开：

1. 多个 Raspberry Pi 节点同时在线的视频回传
2. 摄像头真实关键帧采集和触发策略
3. 真实麦克风与扬声器的语音闭环
4. 本地大模型服务的长时间稳定运行
5. 基于真实实验数据的长时训练任务
6. PC-Pi 在复杂网络环境下的连续联调

上述项目建议在实验室现场以专项联调记录补充。

## 七、结论

基于 2026 年 3 月 8 日的测试结果，NeuroLab Hub 3.0.6 在当前 Windows 构建环境下已满足以下条件：

- 可成功构建主程序、训练入口、便携包和安装包
- 可完成主入口与训练入口的烟测启动
- 可完成 Pi CLI 基础命令层验证
- 可作为当前版本的交付、演示、发布和申报基础

因此，当前版本可认定为“基础功能通过、可交付、可继续现场联调”的软件版本。
