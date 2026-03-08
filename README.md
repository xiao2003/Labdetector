# NeuroLab Hub 3.0.5

## 1. 项目概述

NeuroLab Hub 是一套面向科研实验室的 AI for Science 桌面软件系统，围绕“视觉智能监控 + 语音智能交互 + 知识沉淀 + 模型训练”构建完整闭环。项目按 `pc/` 与 `pi/` 双端拆分：

- `pc/` 负责桌面可视化、专家路由、知识库、实验档案、语音理解、训练工作台与安装交付。
- `pi/` 负责树莓派侧摄像头采集、边缘识别、关键帧回传、语音播报与本地命令行控制。
- PC 与 Pi 通过 WebSocket 协同，实现多节点实验室实时监控、语义分析、风险播报与记录归档。

## 2. 软件定位

NeuroLab Hub 是一个面向实验室场景的软件化平台：

- 多节点可视化监控
- 实验风险语义分析与告警反馈
- 语音智能咨询与流程提示
- 知识库构建、档案沉淀和训练再利用
- LLM 微调与 YOLO 检测模型训练工作台

## 3. 当前交付形态

普通用户在 GitHub Releases 中只需关注三类文件：

- `LabDetector-Setup-vX.Y.Z.exe`
- `LabDetector-vX.Y.Z.zip`
- `LabDetector-Portable-vX.Y.Z.zip`

说明：当前发布文件名沿用历史兼容命名，但软件界面、安装向导和快捷方式展示名统一为 `NeuroLab Hub`。

## 4. 核心闭环

1. PC 扫描并接入 Pi 节点。
2. PC 下发运行策略、专家策略与采集参数。
3. Pi 截取关键帧或推送视频流。
4. PC 完成专家分析、语义提炼与风险判断。
5. 分析结论回传 Pi，以语音或文字方式播报。

## 5. 功能范围

### 5.1 PC 端

- 桌面主界面
- 多 Pi 监控墙与单路视频放大查看
- 专家模型管理
- 多知识库管理
- 云端 / 本地大模型服务配置
- 实验档案中心
- 训练工作台
- 运行自检与依赖自动补齐
- 系统事件流与状态概览

### 5.2 Pi 端

- `start_pi_node.sh` 一键启动
- `pi_cli.py` 命令行自检与启动
- 摄像头采集与关键帧发送
- 与 PC 间的 WebSocket 联动
- 语音采集与播报
- 依赖自检与自动安装

### 5.3 模型与知识能力

- 本地 Ollama 接入
- OpenAI 兼容 API 接入
- LM Studio、vLLM、SGLang、LMDeploy、Xinference、llama.cpp 等本地服务对接
- Qwen、DeepSeek 等国产模型的本地部署与 API 接入路径
- 文本、图片、音频、视频资料导入知识库
- 实验数据导入训练工作台

## 6. 文档索引

- [用户手册](docs/LabDetector_Manual.md)
- [软件说明书](docs/LabDetector软件说明书.md)
- [软件版权声明](docs/LabDetector_Copyright.md)
- [安装包与 EXE 生成教程](docs/EXE与安装包生成教程.md)
- [本地模型服务接入指南](docs/本地模型服务接入指南.md)
- [实验数据集构建规范](docs/实验数据集构建规范.md)
- [GitHub 发布与普通用户下载说明](docs/GitHub发布与普通用户下载说明.md)

