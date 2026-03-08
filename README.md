# NeuroLab Hub —— 面向 AI for Science 的实验室多模态智能中枢 (V3.0.6)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Windows Desktop](https://img.shields.io/badge/Delivery-Windows%20Desktop-1f6feb)](docs/NeuroLab_Hub_用户手册.md)
[![Raspberry Pi](https://img.shields.io/badge/Edge-Raspberry%20Pi-green)](docs/NeuroLab_Hub_软件说明书.md)
[![LLM](https://img.shields.io/badge/LLM-Ollama%20%7C%20LM%20Studio%20%7C%20vLLM-orange)](docs/本地模型服务接入指南.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

NeuroLab Hub 是一个面向科研实验室场景的软件化多模态智能系统。项目以 AI for Science 为核心导向，围绕实验室实时视觉监控、语音智能交互、实验知识沉淀、风险预警提示、实验过程档案化以及用户自有模型训练六条主线持续建设，形成了“PC 智算中枢 + Raspberry Pi 边缘节点 + 专家模型体系 + 多知识库体系 + 训练工作台”的完整工程闭环。

当前版本已经不是单纯的算法原型或命令行脚本集合，而是可直接交付的桌面软件体系：

- 普通用户可以下载安装包或 ZIP，安装后直接使用 `NeuroLab Hub` 主程序与训练工作台。
- 实验室可按需部署多个 Pi 节点，由 PC 端统一扫描、接入、调度和回传分析结果。
- 管理员可通过图形界面接入本地或云端大模型、导入专家模型和知识库、管理训练数据与运行日志。
- 开发者可在 `pc/` 与 `pi/` 双端目录中继续扩展专家能力、知识抽取流水线、训练链路与实验档案体系。

从产品定位上看，NeuroLab Hub 既不是简单的视频监控面板，也不是孤立的大模型问答工具，而是一个面向实验室真实工作流的软件平台。它同时承接多节点现场感知、知识增强分析、语音交互、实验留痕、模型训练与回灌部署，适合实验室日常管理、科研辅助、演示展示和项目申报等场景。

## 1. 核心特性

### 1.1 PC-Pi 双端协同的分布式架构
系统采用中心端与边缘端解耦的部署方式。PC 端负责多节点管理、专家调度、知识检索、训练控制和桌面可视化；Pi 端负责摄像头接入、关键帧上传、边缘语音交互与本地执行控制。该架构既兼顾扩展性，也有利于在多实验位点环境中稳定运行。

### 1.2 面向实验室场景的专家模型体系
系统通过统一专家注册表、专家管理器与闭环协议构建面向实验室业务的可编排专家体系。当前已覆盖危化品识别与提醒、实验仪器操作规范检查、PPE 穿戴、火焰烟雾、液体洒漏、手部姿态、实验问答、设备 OCR、微纳流体与纳米力学分析等能力。

### 1.3 多知识库与多作用域知识增强
系统提供 `common` 公共底座知识库与 `expert.*` 专家专属知识库两级结构，支持文本、Markdown、图片、音频、视频等资料导入。知识库既可以服务实验问答，也可以服务专家分析、风险判断、训练数据沉淀和实验复盘。

### 1.4 可直接交付的桌面软件形态
当前项目同时支持 Windows 安装版、Windows 便携版、PC + Pi 完整包和训练工作台独立入口。发布文件名保留历史兼容命名，但安装器、快捷方式、窗口标题和主界面均统一展示为 `NeuroLab Hub`。

### 1.5 面向真实实验数据的一键训练闭环
系统内置训练工作台，支持 LLM 微调数据导入、识别模型训练数据导入、训练工作区构建、训练依赖自检和一键训练。训练完成后，产物可自动注册并回灌到生产目录，方便用户以真实实验数据持续迭代私有模型。

### 1.6 本地模型优先、云模型兼容的 AI 后端策略
NeuroLab Hub 通过统一 AI 后端接口兼容多类模型服务。除了本地 Ollama，还支持 OpenAI 兼容服务、LM Studio、vLLM、SGLang、LMDeploy、Xinference、llama.cpp 以及云端 API，便于对接 Qwen、DeepSeek 等国产模型。

### 1.7 面向产品运行的结构化日志与自检机制
桌面主界面已将原本跳屏刷新的日志区重构为结构化“系统事件流”，支持按时间、级别、模块和摘要查看系统运行状态。PC 与 Pi 两端均支持启动自检、依赖检测与自动安装，尽可能降低普通用户首次使用门槛。

## 2. 更新日志

### [V3.0.6] 文档体系重构与软件化表述升级版
- 以软件产品视角重写 README、用户手册、软件说明书和版权文档
- 补充根目录 `LICENSE`，恢复并明确仓库级 MIT 开源协议
- 统一项目简介、软件组成、交付形态、训练闭环与档案能力的文档口径
- 强化 README 的目录、部署、接口、文档索引与协议说明

### [V3.0.4] Release 收口与自动发布链路修复
- 修复 GitHub Release 自动上传流程
- 保留安装版、完整版、便携版三类发布物
- 完成面向普通用户的下载说明与发布清单整理

### [V3.0.3] 便携交付与训练运行时补齐
- 引入 `NeuroLab Hub.exe`、`NeuroLab Hub LLM.exe` 等轻量入口
- 补齐训练运行时与本地模型服务预设
- 完善便携 ZIP 交付形态

### [V3.0.2] 训练工作台与本地模型接入增强
- 打通训练工作台链路
- 接入多种本地大模型服务方式
- 强化普通用户的依赖自检与自动安装能力

### [V3.0.1] 桌面化交付热修复
- 修复桌面打包与运行问题
- 调整演示模式、说明文档和软件说明结构

### [V3.0.0] 桌面软件化里程碑版本
- 从早期 CLI / 原型形态升级为 Windows 桌面软件
- 完成 PC / Pi 双端目录拆分
- 引入安装包、启动页、说明页、版权页和软件资源封装

### [V2.6.2] README 工程化整理版
- 重构 README 文档结构
- 梳理专家目录、接口说明与架构边界
- 形成较完整的专家体系工程说明

## 3. 项目定位与应用场景

### 3.1 项目目标
NeuroLab Hub 面向科研实验室管理与科研辅助中的以下核心痛点：

- 缺少连续、稳定、可追溯的实验现场监控体系
- 实验知识高度依赖个人经验，难以沉淀与传承
- 实验人员需要不打断流程的即时语音提示与问答支持
- 通用检测模型难以直接适配实验室专业器具、动作和规则
- 用户需要基于真实实验数据持续训练和部署私有模型
- 实验过程缺少结构化档案，不利于复盘、汇报和知识回灌

### 3.2 典型应用场景
- 实验室安全巡检与异常行为提示
- 危化品操作与实验器具使用规范检查
- 多实验台、多房间、多 Pi 节点集中监控
- 微纳流体与纳米力学实验过程观测和机理分析
- 实验 SOP、设备手册、FAQ 和经验知识管理
- 实验语音咨询、风险播报和过程提示
- 基于真实实验数据的识别模型训练与 LLM 微调
- 面向项目申报、软著材料、答辩演示和成果展示的系统化交付

## 4. 软件组成与交付形态

### 4.1 面向普通用户的交付物
- `NeuroLab-Hub-Setup-vX.Y.Z.exe`：Windows 引导式安装包，支持自定义安装目录
- `NeuroLab-Hub-vX.Y.Z.zip`：PC + Pi 完整包，适合部署完整闭环
- `NeuroLab-Hub-Portable-vX.Y.Z.zip`：Windows 便携包，解压即可使用

### 4.2 安装后的主要入口
- `pc/NeuroLab Hub.exe`：Windows 主程序入口
- `pc/NeuroLab Hub LLM.exe`：LLM 微调入口
- `pc/NeuroLab Hub Vision.exe`：识别模型训练入口
- `pi/start_pi_node.sh`：Pi 节点启动脚本

### 4.3 面向开发者的源码结构
- `pc/`：中心端软件、桌面界面、专家体系、知识库、训练工作台
- `pi/`：边缘节点运行逻辑、摄像头采集、语音交互、自检与通信
- `docs/`：README 配套文档、用户手册、软件说明书、部署与发布说明
- `installer/`：安装器资源、安装信息页和许可文本
- `scripts/`：构建、打包、发布与环境准备脚本

## 5. 总体架构

### 5.1 总体技术路线
NeuroLab Hub 采用“边缘采集 + 中心调度 + 专家研判 + 知识增强 + 训练回灌”的技术路线：

1. Pi 端采集视频流、关键帧、音频和边缘状态。
2. Pi 端根据中心策略上报关键帧、事件与语音内容。
3. PC 端调度专家模型、知识库与大模型后端完成分析。
4. 分析结果以文字或语音形式回传 Pi，或在 PC 本地直接播报。
5. 系统将关键帧、语音轮次、事件记录和分析结果写入实验档案。
6. 用户导入真实实验数据后，可通过训练工作台一键训练并回灌新模型。

### 5.2 当前仓库结构

```text
D:\Labdetector
├─ VERSION
├─ LICENSE
├─ README.md
├─ launcher.py
├─ labdetector.spec
├─ requirements.txt
├─ setup.py
├─ assets/
├─ docs/
├─ installer/
├─ scripts/
├─ pc/
└─ pi/
```

### 5.3 PC 端目录说明

```text
pc/
├─ APP/                        # 打包后的运行时目录
├─ app_identity.py             # 品牌信息与资源路径
├─ desktop_app.py              # 桌面主界面
├─ main.py                     # PC 主入口
├─ communication/              # 节点扫描、WebSocket 与多节点通信
├─ core/                       # 配置、日志、专家管理、档案、AI 后端等底座
├─ experts/                    # 专家模型目录
├─ knowledge_base/             # RAG、结构化知识库与媒体导入
├─ tools/                      # 版本、推送、环境检查等工具
├─ training/                   # 数据导入、工作区构建、训练与模型注册
├─ voice/                      # 语音交互
└─ webui/                      # 运行时、自检、HTTP 接口与控制台
```

### 5.4 Pi 端目录说明

```text
pi/
├─ APP/                        # 打包后的运行时目录
├─ config.py                   # Pi 端配置
├─ config.ini                  # Pi 端运行配置
├─ pi_cli.py                   # Pi 端 CLI 入口
├─ pisend_receive.py           # Pi 端主控制流
├─ start_pi_node.sh            # Pi 一键启动脚本
├─ edge_vision/                # 视频采集、自适应采集、YOLO 检测、运动检测
├─ tools/                      # 版本管理、模型下载等
└─ voice/                      # Pi 端语音识别与播报
```

## 6. 功能模块详解

### 6.1 桌面主界面与监控墙
桌面主界面由 `pc/desktop_app.py` 提供，当前包括以下核心能力：

- 统一显示软件品牌、版本和当前会话状态
- 顶部横向排列核心操作入口
- 左侧运行配置、自检结果和系统概览
- 右侧多 Pi 节点监控墙，支持点击查看单路视频
- 下方结构化系统事件流与详细日志面板
- 知识库、专家模型、训练工作台、模型服务配置等子窗口入口

### 6.2 多节点扫描、接入与通信
相关模块主要位于 `pc/communication/` 和 `pi/pisend_receive.py`，当前已支持：

- 局域网 Pi 节点扫描
- WebSocket 多节点管理
- 中心端策略下发
- 关键帧与事件回传
- 专家分析结果回传 Pi 端
- ACK 闭环、去重和审计记录

系统当前支持的典型链路为：

1. PC 扫描 Pi
2. PC 下发策略
3. Pi 截取关键帧
4. PC 调用专家模型分析
5. 结果回传 Pi 并进行语音 / 文字播报

### 6.3 启动自检与依赖自动安装
PC 与 Pi 两端均提供启动自检流程：

- PC 端在 `pc/webui/runtime.py` 中完成运行时环境、模型服务、知识库目录和训练依赖检查
- Pi 端在 `pi/pisend_receive.py` 与 `pi/pi_cli.py` 中完成依赖探测与自动安装

设计目标是尽可能让普通用户在不单独配置 Python 环境的前提下进入使用流程。

### 6.4 语音智能交互
语音链路主要涉及 `pc/voice/voice_interaction.py`、`pc/core/tts.py` 与 `pi/voice/`：

- 本机摄像头模式下，PC 可直接完成语音采集、理解和播报
- WebSocket 模式下，Pi 可上传语音，PC 理解后返回文本，再由 Pi 播报
- 风险提示可直接转换为语音播报内容
- 单轮对话可自动归档，便于追溯和整理

### 6.5 实验档案中心
实验档案能力位于 `pc/core/experiment_archive.py`，当前档案内容包括：

- 会话元数据
- 关键帧文件
- 事件类型与事件内容
- 风险提示与专家分析结果
- 语音交互内容
- 时间线记录与会话关闭信息

该模块用于支撑实验过程追溯、示范视频制作、实验安全复盘和知识抽取。

### 6.6 知识库系统
知识库能力位于 `pc/knowledge_base/`，主要模块包括：

- `rag_engine.py`：向量检索与知识管理主入口
- `structured_kb.py`：结构化 SQLite 知识库
- `media_ingestion.py`：图片、音频、视频等媒体资料导入与摘要处理

当前知识库支持：

- `common` 公共底座知识库
- `expert.*` 专家专属知识库
- 文本、Markdown、图片、音频、视频导入
- 结构化记录与向量索引并行组织

### 6.7 专家模型体系
专家注册表位于 `pc/core/expert_registry.py`，专家加载由 `pc/core/expert_manager.py` 负责。当前已接入的核心专家包括：

#### A. 实验室安全规范相关专家
- `safety.chem_safety_expert`：危化品识别与合规提醒
- `safety.equipment_operation_expert`：仪器操作规范检查
- `safety.flame_fire_expert`：火焰烟雾风险提示
- `safety.general_safety_expert`：通用实验室安全行为识别
- `safety.hand_pose_expert`：手部姿态语义支撑
- `safety.integrated_lab_safety_expert`：综合安全聚合专家
- `safety.ppe_expert`：PPE 穿戴规范检查
- `safety.spill_detection_expert`：液体洒漏检测

#### B. 实验知识与问答相关专家
- `lab_qa_expert`：实验室问答与记录检索
- `equipment_ocr_expert`：设备铭牌、标签与文档 OCR

#### C. AI for Science 研究辅助相关专家
- `nanofluidics.microfluidic_contact_angle_expert`：微纳流体接触角分析
- `nanofluidics.nanofluidics_multimodel_expert`：微纳力学多模型综合分析

### 6.8 AI 后端与模型服务
AI 后端主入口位于 `pc/core/ai_backend.py`。当前支持：

- Ollama 本地推理
- OpenAI 兼容接口
- LM Studio
- vLLM
- SGLang
- LMDeploy
- Xinference
- llama.cpp
- OpenAI、DeepSeek 等云端接口

### 6.9 训练工作台
训练相关模块位于 `pc/training/`，当前支持：

- 导入 LLM 微调语料
- 导入 YOLO 检测训练数据
- 构建训练工作区
- 检查训练依赖与本地运行时
- 启动训练任务
- 记录训练日志
- 自动注册训练结果并回灌运行目录

## 7. 接口与运行闭环说明

### 7.1 PC 扫描 Pi 到结果回传的主闭环
1. PC 启动后扫描 Pi 节点并建立连接。
2. 管理员在 PC 端选择运行模式、专家配置和策略。
3. PC 下发策略到各 Pi 节点。
4. Pi 端在摄像头、YOLO 或边缘规则触发时截取关键帧并上报事件。
5. PC 接收事件后调用专家模型、知识库和大模型完成分析。
6. 分析结果记录到系统事件流和实验档案。
7. 结果通过 WebSocket 回传到 Pi 端，由 Pi 完成语音或文字播报。

### 7.2 语音交互闭环
- WebSocket 模式：Pi 端采集语音 -> PC 端 ASR / LLM / TTS -> 文本和播报结果回传 Pi
- 本机摄像头模式：PC 端本地采集语音 -> 本地理解 -> 本地播报

### 7.3 知识增强闭环
1. 管理员导入公共知识库和专家知识库资料。
2. 系统将资料归档并写入向量索引或结构化库。
3. 专家分析和实验问答过程调用对应知识作用域。
4. 新生成的实验记录、经验总结和多媒体摘要可继续回灌知识库。

### 7.4 训练回灌闭环
1. 用户导入真实实验数据。
2. 训练工作台构建训练工作区。
3. 用户执行 LLM 微调或 YOLO 训练。
4. 系统输出模型产物和训练日志。
5. 新模型注册后可重新投入生产使用。

## 8. 硬件准备与部署清单

### 8.1 中心计算节点（PC 端）
- 操作系统：Windows 10 / Windows 11，64 位
- CPU：8 核以上推荐
- 内存：32GB 及以上推荐
- GPU：建议 NVIDIA RTX 3090 / 4090 / 5090 或同等级设备
- 存储：建议预留 50GB 以上空间，用于模型、知识库、训练与归档
- 网络：可与 Pi 节点处于同一局域网

### 8.2 边缘节点（Pi 端）
- 设备：Raspberry Pi 4B / 5 或同等级 ARM Linux 设备
- 摄像头：CSI 或 USB 摄像头
- 存储：建议 32GB 以上
- 网络：稳定局域网连接
- 音频：麦克风与扬声器或语音模块

### 8.3 模型服务侧
- 本地模型优先：Ollama、LM Studio、vLLM、SGLang、LMDeploy、Xinference 等
- 云端模型备选：OpenAI、DeepSeek 及其他 OpenAI 兼容接口
- 推荐文本模型：Qwen、DeepSeek 系列
- 推荐视觉链路：Qwen2.5-VL 或其他 OpenAI 兼容多模态服务

## 9. 上手指南

### 9.1 下载方式
- 普通用户：下载 Release 中的安装版或 ZIP
- 技术用户：下载完整包并按需配置模型服务
- 开发者：直接克隆源码仓库

### 9.2 Windows 安装版
1. 下载 `NeuroLab-Hub-Setup-vX.Y.Z.exe`
2. 双击进入安装向导
3. 选择安装目录
4. 完成安装后启动 `NeuroLab Hub`

### 9.3 Windows 便携版
1. 下载 `NeuroLab-Hub-Portable-vX.Y.Z.zip`
2. 解压到任意目录
3. 进入 `pc/`
4. 双击 `NeuroLab Hub.exe`

### 9.4 完整闭环部署
1. 下载 `NeuroLab-Hub-vX.Y.Z.zip`
2. 将 `pc/` 部署到 Windows 主机
3. 将 `pi/` 部署到 Raspberry Pi
4. PC 启动主程序
5. Pi 执行 `./start_pi_node.sh start --auto-install-deps`
6. 在 PC 上完成节点扫描和策略下发

### 9.5 首次启动建议
1. 先执行系统自检
2. 配置 AI 后端和模型服务
3. 导入公共知识库和专家知识库
4. 根据实验室场景启用对应专家
5. 再进入正式监控或训练流程

## 10. 数据、知识库与训练闭环

### 10.1 数据来源
- Pi 节点采集的视频帧与关键帧
- 实验问答与语音交互记录
- SOP、说明书、标签、FAQ 和历史实验资料
- 用户手工上传的图片、音频、视频与文本文档
- 训练工作台导入的标注数据和语料数据

### 10.2 知识库作用域设计
- `common`：公共背景知识、共性规则、实验室基础规范
- `expert.*`：某一类专家模型的专属知识

### 10.3 媒体知识导入设计
当前系统支持将图片、音频、视频作为知识资料导入，并记录原文件、元数据和摘要说明。后续可继续增强 OCR、ASR、关键帧抽取、时间轴摘要和 SOP 自动提炼能力。

### 10.4 一键训练设计
系统当前已经支持用户基于真实实验数据进行：

- LLM 领域适配微调
- 识别模型训练
- 训练产物注册与回灌部署

## 11. 本地与云端大模型服务

### 11.1 本地模型优先策略
为了兼顾数据安全、实验隐私和离线可用性，NeuroLab Hub 默认鼓励优先使用本地大模型服务。常见组合包括：

- Ollama：快速启动本地文本模型
- LM Studio：适合桌面端图形化管理本地模型
- vLLM / SGLang / LMDeploy：适合高吞吐本地推理
- Xinference：适合统一管理多类模型服务
- llama.cpp：适合轻量本地部署

### 11.2 国产模型接入建议
- 文本主模型：Qwen、DeepSeek 系列
- 视觉问答与多模态补充：Qwen2.5-VL 或兼容服务
- 云端 API：DeepSeek API、OpenAI 兼容接口

详细接入说明见 `docs/本地模型服务接入指南.md`。

## 12. 测试、运维与日志

### 12.1 当前建议测试路径
1. 先验证 PC 端主程序与两个训练入口是否能正常启动。
2. 再验证知识库导入、专家加载与模型服务连接。
3. 随后联调 Pi 节点启动、自检、摄像头接入与 WebSocket 通信。
4. 最后验证完整闭环，包括关键帧上报、专家分析、语音播报与实验档案写入。

### 12.2 当前版本已完成的基础验证（2026-03-08）
- `pc/NeuroLab Hub.exe` 启动烟测通过
- `pc/NeuroLab Hub LLM.exe` 启动烟测通过
- `pc/NeuroLab Hub Vision.exe` 启动烟测通过
- `pi/pi_cli.py self-check --help` 与 `start --help` 参数解析通过
- 核心 Python 入口文件语法编译通过
- `scripts/build_desktop_exe.ps1`、`scripts/build_portable_zip.ps1`、`scripts/build_installer.ps1` 均已重建成功

### 12.3 日志与追溯
- 桌面界面提供结构化系统事件流
- 训练工作台记录训练日志
- 语音交互支持按轮次归档
- 实验档案记录关键帧、事件和分析结果

### 12.4 运维建议
- 定期备份知识库、实验档案和训练产物
- 在更新模型服务前做一次连通性验证
- 对关键实验位点保留稳定的 Pi 网络与供电环境

## 13. 文档索引

- `README.md`：项目总说明
- `docs/NeuroLab_Hub_用户手册.md`：用户手册
- `docs/NeuroLab_Hub_软件说明书.md`：软件说明书
- `docs/NeuroLab_Hub_软著申请材料.md`：软著申请材料整理稿
- `docs/NeuroLab_Hub_测试实例.md`：测试实例
- `docs/NeuroLab_Hub_测试报告.md`：测试报告
- `docs/NeuroLab_Hub_版权声明.md`：版权声明
- `docs/NeuroLab_Hub_软件版权声明.md`：版权声明副本
- `docs/本地模型服务接入指南.md`：本地模型服务接入说明
- `docs/实验数据集构建规范.md`：实验数据集构建规范
- `docs/EXE与安装包生成教程.md`：EXE 与安装包生成教程
- `docs/GitHub发布与普通用户下载说明.md`：发布与下载说明
- `docs/项目规划对照整改表.md`：项目规划对照整改表

## 14. 开源协议与版权说明

### 14.1 开源协议
本项目仓库代码采用 **MIT License** 开源，详见根目录 [LICENSE](LICENSE)。

### 14.2 第三方组件
项目在开发、构建或运行过程中可能使用 Python、Tk、OpenCV、Pillow、PyInstaller、Transformers、PEFT、Ultralytics、LangChain、Ollama 生态相关组件及其他第三方开源软件。相关第三方组件的版权和许可归各自权利人所有，使用时应遵循其原始协议。

### 14.3 软件与文档版权
程序代码、界面设计、图形图标、安装器资源、说明文档及相关说明文字由 NeuroLab Hub 软件研发组持续整理与维护。若用于论文汇报、项目申报、软著材料编写或产品演示，建议结合 `docs/` 目录中的软件说明书、用户手册、版权声明一并使用。

## 15. 致谢

感谢实验室场景中长期沉淀的业务需求、真实实验数据与测试反馈，也感谢 Python、Ollama、OpenCV、PyInstaller、Transformers、Ultralytics 及相关开源社区提供的基础能力支持。
