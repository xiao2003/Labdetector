# NeuroLab Hub——可编排专家模型的实验室多模态智能中枢 测试实例

版本：3.0.6  
编写日期：2026 年 3 月 8 日

## 一、说明

本文件用于整理 NeuroLab Hub 这一“可编排专家模型的实验室多模态智能中枢”当前版本的核心测试实例，覆盖主程序启动、训练入口启动、Pi CLI、打包构建和软件基本可用性。该文档用于测试组织、答辩展示、软著材料和版本验收。

## 二、测试环境

### 2.1 PC 端环境

- 操作系统：Windows 10 64 位
- Python：`C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`
- 打包工具：PyInstaller 6.19.0
- 安装器：Inno Setup 6.7.1
- 测试目录：`D:\Labdetector`

### 2.2 Pi 端环境说明

当前测试实例中的 Pi 端命令验证基于 CLI 层面完成。涉及摄像头、麦克风、扬声器和局域网联调的用例，应在真实 Raspberry Pi 设备上补充现场联调记录。

## 三、测试实例列表

### T01 主程序启动烟测

- 目标：验证 `pc/NeuroLab Hub.exe` 能在无交互烟测模式下正常启动并退出
- 前置条件：主程序 EXE 已构建完成
- 步骤：
  1. 运行 `NeuroLab Hub.exe --smoke-test-file <输出文件>`
  2. 等待程序退出
  3. 检查输出文件是否生成
- 预期结果：
  - 进程退出码为 0
  - 烟测输出文件生成

### T02 LLM 工作台启动烟测

- 目标：验证 `pc/NeuroLab Hub LLM.exe` 能正常启动并退出
- 前置条件：LLM 工作台 EXE 已构建完成
- 步骤：
  1. 运行 `NeuroLab Hub LLM.exe --smoke-test-file <输出文件>`
  2. 等待程序退出
  3. 检查输出文件是否生成
- 预期结果：
  - 进程退出码为 0
  - 烟测输出文件生成

### T03 识别模型工作台启动烟测

- 目标：验证 `pc/NeuroLab Hub Vision.exe` 能正常启动并退出
- 前置条件：识别模型工作台 EXE 已构建完成
- 步骤：
  1. 运行 `NeuroLab Hub Vision.exe --smoke-test-file <输出文件>`
  2. 等待程序退出
  3. 检查输出文件是否生成
- 预期结果：
  - 进程退出码为 0
  - 烟测输出文件生成

### T04 Pi CLI 自检帮助命令

- 目标：验证 Pi 端自检入口可正确解析参数
- 步骤：
  1. 执行 `python pi/pi_cli.py self-check --help`
- 预期结果：
  - 返回帮助信息
  - 显示 `--auto-install-deps` 和 `--no-auto-install-deps`

### T05 Pi CLI 启动帮助命令

- 目标：验证 Pi 端启动入口可正确解析关键参数
- 步骤：
  1. 执行 `python pi/pi_cli.py start --help`
- 预期结果：
  - 返回帮助信息
  - 显示 `--pc-ip`、`--ws-port`、`--weights-path` 等参数

### T06 Python 入口文件语法编译测试

- 目标：验证核心入口文件不存在语法错误
- 覆盖文件：
  - `launcher.py`
  - `pc/main.py`
  - `pc/desktop_app.py`
  - `pc/webui/runtime.py`
  - `pc/core/ai_backend.py`
  - `pc/training/runtime_env.py`
  - `pc/training/train_manager.py`
  - `pi/pi_cli.py`
  - `pi/pisend_receive.py`
- 预期结果：
  - 全部文件编译通过

### T07 Windows 主程序打包

- 目标：验证桌面 EXE 构建链有效
- 步骤：
  1. 执行 `scripts/build_desktop_exe.ps1`
- 预期结果：
  - 生成 `pc/NeuroLab Hub.exe`
  - 生成 `pc/NeuroLab Hub LLM.exe`
  - 生成 `pc/NeuroLab Hub Vision.exe`
  - 生成完整 ZIP 包

### T08 Windows 便携包打包

- 目标：验证便携 ZIP 构建链有效
- 步骤：
  1. 执行 `scripts/build_portable_zip.ps1`
- 预期结果：
  - 成功生成 `NeuroLab-Hub-Portable-v3.0.6.zip`

### T09 Windows 安装包打包

- 目标：验证引导式安装包可正常生成
- 步骤：
  1. 执行 `scripts/build_installer.ps1`
- 预期结果：
  - 成功生成 `NeuroLab-Hub-Setup-v3.0.6.exe`

### T10 安装器基础内容验证

- 目标：验证安装器中包含主程序、训练入口和运行时目录
- 检查项：
  - `NeuroLab Hub.exe`
  - `NeuroLab Hub LLM.exe`
  - `NeuroLab Hub Vision.exe`
  - `pc/APP`
- 预期结果：
  - 安装器编译阶段可见上述内容被打包

### T11 主界面信息一致性验证

- 目标：验证主界面品牌、说明文档和版本号口径一致
- 检查项：
  - 软件名称显示为 `NeuroLab Hub`
  - 顶部操作区采用横向排列
  - 软件说明、用户手册、版权页面与版本号一致
- 预期结果：
  - 不出现旧项目名或旧版本号

### T12 日志面板展示验证

- 目标：验证日志区与主面板融合，并以结构化方式展示
- 检查项：
  - 不出现持续跳屏刷新
  - 以时间、级别、模块和摘要形式展示
- 预期结果：
  - 适合长时间查看和正式演示

### T13 知识库导入流程验证

- 目标：验证知识库支持按公共和专家作用域组织资料
- 检查项：
  - `common` 公共底座知识库
  - `expert.*` 专家知识库
- 预期结果：
  - 用户可按作用域导入对应资料

### T14 训练入口可用性验证

- 目标：验证用户可通过独立 EXE 进入训练工作台
- 检查项：
  - LLM 训练入口可打开
  - 识别模型训练入口可打开
  - 训练入口名称与功能一致
- 预期结果：
  - 普通用户无需手工进入源码目录即可开始训练流程

### T15 真实设备联调用例

- 目标：验证 PC-Pi 完整闭环
- 步骤：
  1. Pi 启动自检和服务
  2. PC 扫描并接入 Pi
  3. PC 下发策略
  4. Pi 截取关键帧并上报
  5. PC 完成专家分析
  6. 结果回传 Pi 语音/文字播报
- 预期结果：
  - 完成完整闭环

说明：该用例依赖真实网络、摄像头、麦克风和扬声器，需在现场联调环境补充记录。

## 四、证据留存建议

建议为每个测试实例保留以下证据：

1. 执行命令截图
2. 主界面或命令输出截图
3. 烟测输出文件
4. 打包产物文件名和大小记录
5. 关键日志或事件流截图

## 五、结论

当前版本的测试实例已经覆盖软件的主入口、训练入口、Pi CLI、打包链路和基础产品表现，可作为测试组织和申报材料中的实例清单使用。

