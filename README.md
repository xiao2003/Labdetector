# NeuroLab Hub —— 基于可编排专家模型的实验室多模态智能中枢 (V1.0.0)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Windows Desktop](https://img.shields.io/badge/Delivery-Windows%20Desktop-1f6feb)](docs/NeuroLab_Hub_项目总览与使用手册.md)
[![Raspberry Pi](https://img.shields.io/badge/Edge-Raspberry%20Pi-green)](docs/NeuroLab_Hub_项目总览与使用手册.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

NeuroLab Hub 是面向科研实验室场景构建的分布式多模态智能系统。系统采用 `PC` 中心端与 `Raspberry Pi` 边缘节点协同架构，覆盖实验现场监控、专家模型编排、知识导入、训练工作台、语音交互、视觉闭环和实验档案沉淀。

当前 `1.0.0` 正式基线已经收敛为：

1. Windows 端以 `Setup.exe` 安装包作为正式交付形态。
2. `Pi` 端复制 `pi/` 目录即可启动边缘节点。
3. GUI 先显示，固定管家层模型在后台下载和后台预热。
4. 用户在 GUI 中只选择执行层模型，固定管家层模型不暴露。
5. `PC-Pi` 语音/视频闭环已统一收敛到单一编排主链。

## 当前正式交付形态

- 安装包：`NeuroLab-Hub-Setup-v1.0.0.exe`
- 便携包：`NeuroLab_Hub_1.0.0.zip`
- 复验包：`NeuroLab_Hub_1.0.0_fresh_validation.zip`
- Pi：`pi/` 目录整体复制

普通用户优先使用安装包。便携包用于需要解压即用的场景。

## 首次启动说明

首次启动时：

- 主界面会先显示
- 固定管家层模型不会阻塞 GUI
- 系统会在后台检查 `llama.cpp` runtime、后台下载固定 GGUF、后台预热模型
- 管家层未就绪前，系统使用确定性规则链继续工作

## 当前闭环能力

### 1. 语音闭环

1. Pi 本地离线识别音频为文本
2. 文本上行到 PC
3. PC 进入固定管家层编排
4. 再由执行层模型或专家执行链生成回答
5. 结果回传 Pi
6. Pi 本地播报

### 2. 视频闭环

1. Pi 低频前置检测
2. 危险事件或用户主动请求时上传关键帧
3. PC 进入固定管家层编排
4. 专家模型与知识库完成分析
5. 结果回传 Pi 并完成播报/ACK

## 当前正式边界

- 多节点目前以虚拟 Pi 和文件驱动链路验证为主
- 某些第三方语音扩展板存在兼容性风险，不纳入本版本正式通过项
- 真实麦克风阵列、真实扬声器阵列、实机集群长期联调仍需后续继续完成

## 核心文档

- [项目总览与使用手册](docs/NeuroLab_Hub_项目总览与使用手册.md)
- [测试与发布手册](docs/NeuroLab_Hub_测试与发布手册.md)
- [版权与软著材料](docs/NeuroLab_Hub_版权与软著材料.md)
- [文档归档索引](docs/archive/README.md)
