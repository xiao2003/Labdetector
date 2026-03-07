# LabDetector 3.0.2

## 1. 项目概述

### 1.1 产品定位

LabDetector 是一个面向实验室场景的 AI for Science 智能监控与语音交互系统，代码按 `pc/` 与 `pi/` 双端拆分：

- `pc/` 负责桌面可视化、专家模型调度、知识库检索、训练工作台与安装打包。
- `pi/` 负责树莓派侧视频采集、边缘识别、语音交互与本地控制。
- PC 与 Pi 通过 WebSocket 协同，实现多节点监控、风险预警、语音问答与知识沉淀。

### 1.2 核心能力

当前版本已具备以下核心能力：

- 多树莓派节点扫描、接入与可视化监控墙展示
- 本机摄像头模式与树莓派集群 WebSocket 模式
- 多专家模型路由、中文专家名称展示、专家资产导入
- 公共知识库 `common` 与专家专属知识库 `expert.*`
- 语音识别、语音合成、风险事件回传播报
- 实验档案中心、语音轮次归档、训练工作台
- 本地 Ollama、本地微调适配器与多种云端大模型接入

### 1.3 主闭环

系统支持以下主业务闭环：

1. PC 扫描 Pi 节点并建立连接。
2. PC 向 Pi 下发专家策略与运行配置。
3. Pi 采集视频流并在边缘侧截取关键帧或触发事件。
4. PC 接收关键帧与事件，调用专家模型分析并生成结论。
5. PC 将语音/文字结论回传给 Pi，由 Pi 端进行播报。

### 1.4 知识库与专家模型

系统内置多知识库架构：

- 公共背景知识库：`common`
- 专家专属知识库：`expert.<expert_code>`
- 支持通过界面和 HTTP 接口直接导入文本、图片、音频、视频等资料
- 图片、音频、视频导入时会生成结构化摘要与 sidecar 元数据，便于后续检索和训练

### 1.5 语音交互

语音能力覆盖两种模式：

- Pi 端 WebSocket 语音交互：Pi 采集语音，PC 理解与生成回答，再回传 Pi 播报
- PC 本机摄像头模式语音交互：PC 端直接完成本地语音采集、理解与播报
- 单轮对话按轮次归档至 `pc/log/voice_rounds/`
- 风险事件可自动转为语音播报，形成“视觉感知 -> 语音响应”的闭环

## 2. 版本说明

- `3.0.2` 为当前桌面软件化版本，仓库结构以 `pc/` 和 `pi/` 为主。
- 本版本补齐了实验档案中心、训练工作台、训练数据导入、GitHub Release 发布流程和打包文档。

## 3. 目录结构

### 3.1 源码结构

```text
D:\Labdetector
├─ pc/
├─ pi/
├─ docs/
├─ assets/
├─ installer/
├─ scripts/
├─ launcher.py
├─ labdetector.spec
├─ requirements.txt
└─ README.md
```

### 3.2 关键目录

- `pc/desktop_app.py`：桌面软件主界面
- `pc/webui/runtime.py`：运行时主控、监控链路、训练接口
- `pc/webui/server.py`：本地 HTTP 接口
- `pc/core/experiment_archive.py`：实验档案中心
- `pc/core/voice_round_archive.py`：语音轮次归档
- `pc/training/`：训练数据构建、数据导入、LLM 微调、Pi 检测模型微调
- `pc/knowledge_base/`：知识库导入、媒体语义摘要
- `pi/pisend_receive.py`：Pi 端视频/控制链路
- `pi/pi_cli.py`：Pi 端命令行工具

### 3.3 运行时数据

运行后会生成以下目录：

- `pc/log/experiment_archives/`：实验档案
- `pc/log/voice_rounds/`：语音轮次归档
- `pc/training_runs/`：训练工作区
- `pc/training_assets/`：导入的真实训练数据
- `pc/models/llm_adapters/`：已注册的本地 LLM 微调适配器
- `pc/models/registry/`：训练部署清单与激活状态
- `pc/knowledge_base/scopes/`：知识库作用域
- `pi/models/detectors/`：Pi 端检测模型权重

## 4. 专家模型与知识库

### 4.1 专家模型

专家模型通过 `pc/core/expert_registry.py` 管理，界面与接口均显示中文名称而非 `xxx.py` 文件名。

### 4.2 知识库作用域

- 公共背景知识库
- 安全合规专家知识库
- 仪器操作专家知识库
- 实验流程专家知识库
- 视觉语义与风险分析相关知识库

### 4.3 导入方式

支持两种导入方式：

- 桌面端界面导入
- HTTP 接口导入

### 4.4 媒体资料导入

- 图片：生成尺寸、模式、语义摘要与关键词
- 音频：生成时长、采样率、语义摘要与关键词
- 视频：生成分辨率、帧数、时长、语义摘要与关键词

### 4.5 训练数据导入与生产联动

- LLM 微调数据：支持 `jsonl / json / csv / txt / md`
- Pi 检测模型数据：支持 YOLO 数据集目录、压缩包或带标注图片目录
- 导入后统一收敛到 `pc/training_assets/`
- 训练工作区会自动合并“真实导入数据 + 运行归档样本”
- LLM 微调基于 `Transformers + Datasets + PEFT(LoRA)`
- Pi 检测模型微调基于 `Ultralytics YOLO`
- 微调成功后，系统会自动将 LLM 适配器注册到 `pc/models/llm_adapters/`，并可作为“本地微调适配器”后端投入语音问答与知识检索场景
- Pi 检测模型训练成功后，系统会自动将权重部署到 `pi/models/detectors/`，并写入 Pi 配置作为默认检测权重

### 4.6 导入接口

- `POST /api/experts/import`
- `POST /api/knowledge/import`
- `POST /api/training/import-llm`
- `POST /api/training/import-pi`

## 5. 运行机制与接口

### 5.1 Pi 监控链路

PC 扫描到树莓派后，会通过 `CMD:SYNC_POLICY` 下发专家策略，再等待 Pi 回传关键帧事件与语音指令。

### 5.2 事件通道

系统当前使用的核心报文包括：

- `PI_CAPS`
- `PI_EXPERT_EVENT`
- `PI_YOLO_EVENT`
- `PI_VOICE_COMMAND`
- `PI_EXPERT_ACK`
- `CMD:TTS`
- `CMD:SYNC_POLICY`

### 5.3 档案与训练接口

- `GET /api/archives`
- `GET /api/archives/<session_id>`
- `GET /api/training`
- `POST /api/training/workspace`
- `POST /api/training/import-llm`
- `POST /api/training/import-pi`
- `POST /api/training/activate-llm`
- `POST /api/training/activate-pi`
- `POST /api/training/llm`
- `POST /api/training/pi`
- `POST /api/training/run-all`

## 6. 环境要求

### 6.1 PC 端

- Windows 10/11
- Python 3.11
- 建议具备 NVIDIA GPU
- 建议具备麦克风与扬声器

### 6.2 Raspberry Pi 端

- Raspberry Pi 4/5
- 摄像头
- 麦克风 / 扬声器
- 可用的局域网环境

### 6.3 关键依赖

- `numpy`
- `opencv-python`
- `pillow`
- `websockets`
- `SpeechRecognition`
- `vosk`
- `pyttsx3`
- 按需安装：`transformers`、`peft`、`datasets`、`ultralytics`

## 7. 使用说明

### 7.1 开发者获取源码

```powershell
git clone https://github.com/xiao2003/Labdetector.git D:\Labdetector
cd D:\Labdetector
```

开发者主要使用源码仓库进行调试、训练与二次开发。

### 7.2 普通用户下载方式

普通用户不要下载源码压缩包，直接进入 GitHub Releases 页面下载安装器：

- Release 页面：<https://github.com/xiao2003/Labdetector/releases>
- 选择最新版 `LabDetector-Setup-vX.Y.Z.exe`

### 7.3 安装后的目录形态

安装完成后，用户电脑上的软件结构是：

```text
安装目录
├─ LabDetector.exe
└─ APP
```

其中：

- `LabDetector.exe` 是用户双击启动的唯一主程序
- `APP` 为隐藏运行时目录，包含程序依赖、文档和资源

### 7.4 一键训练

桌面端“训练工作台”支持：

1. 导入真实语料与标注数据
2. 构建统一训练工作区
3. 启动 LLM LoRA 微调
4. 启动 Pi 检测模型微调
5. 一键顺序执行全流程训练
6. 自动注册并激活最新训练产物

### 7.5 生成 EXE 与安装包

详见 [docs/EXE与安装包生成教程.md](docs/EXE与安装包生成教程.md)。

常用命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_desktop_exe.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

### 7.6 GitHub Release 发布

仓库已提供 GitHub Actions 自动发布工作流。推荐发布方式：

1. 提交并推送代码到 `master`
2. 打版本标签，例如 `v3.0.2`
3. 推送标签到 GitHub
4. GitHub Actions 自动构建：
   - `pc/LabDetector.exe`
   - `LabDetector-vX.Y.Z.zip`
   - `LabDetector-Setup-vX.Y.Z.exe`
5. GitHub 自动创建 Release，普通用户只需下载安装器

### 7.7 用户手册

- [docs/LabDetector_Manual.md](docs/LabDetector_Manual.md)
- [docs/LabDetector软件说明书.md](docs/LabDetector软件说明书.md)

## 8. AI for Science 对照与当前状态

### 8.1 已对齐能力

- PC-Pi 视觉闭环
- 语音交互闭环
- 多知识库与专家模型
- 桌面可视化监控墙
- 云/本地模型接入
- 实验档案与语音轮次归档
- 一键训练工作台

### 8.2 重点研究方向

当前版本已具备研究平台基础，后续重点可继续深化：

- 更高质量的实验室专用数据集采集与标注
- 行为识别与实验步骤时序建模
- 图片/音频/视频到知识条目的深层语义抽取
- 面向科研场景的机理分析、实验解释与研究辅助能力

### 8.3 说明

本项目当前已经超出“桌面软件演示原型”阶段，具备真实部署、知识导入、档案归档和训练微调能力，但最终效果仍取决于真实实验数据质量、标注规范和底座模型选择。


