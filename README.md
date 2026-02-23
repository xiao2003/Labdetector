# LabDetector：智能多模态实验室管家 (V2.0)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/AI_Engine-Ollama-white)](https://ollama.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LabDetector 是专为微纳流体力学及重型科研实验室打造的**分布式智能多模态管家系统**。它将边缘计算（树莓派节点）与高性能中心算力（RTX 5090）相结合，支持**动态 QoS 视频并发、RAG 私有知识库、以及完全断网环境下的离线语音交互**。

它不仅是一个监控系统，更是陪伴你进行科学研究、沉淀实验资产的 AI 师兄。


## 核心特性

* **动态 QoS 多节点并发 (边缘计算)**：
  支持 1~N 台树莓派无线接入。主控 PC 根据节点数量自动下发指令，动态调配边缘端摄像头帧率（如 5台设备自动锁定 6FPS），确保 Wi-Fi 带宽永不拥塞，极低 CPU 占用率（稳定 30FPS 渲染）。
* **RAG 实验资产累积体系 (长时记忆)**：
  自带基于 FAISS 的轻量化本地向量数据库。随时随地通过语音说出实验记录，系统自动保存为 `.txt` 实体文件并一秒入库。未来可随时跨时间线检索过往的任何一句话。
* **Vosk 极速离线语音核心 (离线可用)**：
  采用本地轻量级 Vosk 模型进行语音识别，彻底摆脱外部网络依赖。具备自动寻址系统麦克风、强制接管独占通道、智能降噪防干扰等特性。支持“打断式连续听写”。
* **异步非阻塞多模态大模型视觉**：
  GUI 画面渲染与底层大模型（如 Qwen-VL, Llava）推理彻底解耦。PC 算力池按顺序调度各节点帧流，告别卡顿。

## 项目目录结构

系统采用了高内聚、低耦合的模块化设计，完美分离了底层通信、视觉 AI、语音交互与 RAG 引擎。

```text
Labdetector/
├── launcher.py                 # 系统高内聚一键启动器 (自带预加载与依赖检测)
├── setup.py                    # 项目包安装与全局注册脚本
├── requirements.txt            # 极简项目依赖清单 (自动剥离冗余环境)
├── config.ini                  # 全局配置文件 (系统首次启动自动生成)
│
├── pcside/                     # PC 主控端核心代码库
│   ├── main.py                 # 主控中心循环 (含视频并发调度与非阻塞推理)
│   ├── log/                    # 系统自动生成的本地运行日志 (按时间戳存档)
│   │
│   ├── core/                   # 核心基础能力模块
│   │   ├── ai_backend.py       # 大模型视觉分析与多模态问答接口封装
│   │   ├── tts.py              # 文本转语音引擎 (TTS)
│   │   ├── config.py           # 配置文件读写管理器
│   │   └── logger.py           # 终端高亮日志与打印流接管控制
│   │
│   ├── communication/          # 网络与分布式通信模块
│   │   ├── network_scanner.py  # UDP 局域网树莓派自动扫描与拓扑构建
│   │   └── multi_ws_manager.py # WebSocket 多节点全双工并发管理器 (含 QoS 动态帧率控制)
│   │
│   ├── knowledge_base/         # RAG 本地知识库与长时记忆模块
│   │   ├── rag_engine.py       # FAISS 向量数据库核心引擎
│   │   ├── docs/               # 自动保存的实验语音记录 (TXT 实体存档)
│   │   └── faiss_index/        # 序列化后的本地向量二进制数据
│   │
│   └── voice/                  # 🎤 独立智能语音中枢
│       ├── voice_interaction.py# 双路语音引擎 (离线唤醒+打断听写+意图路由)
│       └── model/              # Vosk 离线轻量级中文语音识别模型 (高内聚封装)
│
├── piside/                     # 树莓派边缘端代码库
│   └── pisend_receive.py       # 边缘端全双工收发器 (动态压帧视频推流 + 接收分析播报)
│
└── tools/                      # 开发者工具箱
    ├── push.py                 # 自动化安全 Git 推送脚本 (防大文件、防断网)
    ├── check_gpu.py            # 本地算力与 CUDA 探针环境校验
    └── check_mic.py            # Windows 麦克风物理独占与连通性测试仪

## 硬件准备与部署清单

本系统采用“云-边-端”协同架构，为了保证大模型推理与多路视频流的极低延迟，建议采用以下硬件配置：

### 1. 中心计算枢纽 (PC 端)
负责全过程的 AI 视觉推理、RAG 向量检索、Vosk 离线语音解析与 GUI 渲染。
* **显卡 (GPU)**: 强烈推荐 NVIDIA RTX 4090 / 5090 或同等 24GB+ 显存的设备（用于满载运行 Ollama 多模态视觉模型）。
* **内存 (RAM)**: 32GB 及以上（保障多节点视频帧缓存与本地向量数据库常驻内存）。
* **外设交互**: 
  * 独立麦克风（或带麦克风的耳机），用于随时通过唤醒词触发交互。
  * 扬声器 / 音响，用于接收 TTS 智能语音播报反馈。
* **操作系统**: Windows 10/11 或 Ubuntu 22.04（需配置好完整的 CUDA 环境）。

### 2. 边缘监控节点 (树莓派集群，1~N 台)
负责实验室各个点位的视频采集、视频流高压缩传输及本地 TTS 语音响应。
* **主板**: Raspberry Pi 4B 或 Raspberry Pi 5（需自带 Wi-Fi 模块）。
* **摄像头**: 树莓派官方 CSI 摄像头模块（推荐 Camera Module V2 或 HQ 摄像头，兼容 `picamera2` 库）。
* **音频输出 (可选)**: 通过 3.5mm 接口或蓝牙连接小型音箱，用于播放主控端下发的 AI 警告指令。
* **电源**: 官方 15W / 27W Type-C 电源，防止满载录像时掉电死机。

### 3. 网络环境 (极度重要)
* **局域网路由**: 建议使用 Wi-Fi 6 (802.11ax) 千兆路由器，所有设备必须处于**同一个局域网 (同一网段)** 下。由于系统采用了智能 QoS 动态调频技术，常规家用/实验室路由器即可稳定带载 5 台以上的监控节点并发。

## 上手指南
### 1. 基础环境
请确保安装了 Python 3.9 以上版本。克隆本项目后，在项目**根目录**执行：
```bash
# 自动安装全部必需依赖包，并将模块注册至全局
pip install -e .
```
GPU 加速提示：RAG 依赖的 sentence-transformers 默认自带 CPU 版的 Pytorch。若要开启向量处理的 CUDA 加速，请手动覆盖安装 PyTorch：
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
### 2. 本地AI引擎准备
大模型驱动：安装 Ollama:https://ollama.com/ 并拉取多模态模型：ollama run llava:7b-v1.5-q4_K_M
离线语音驱动：默认上传，如果缺失，下载 vosk-model-small-cn-0.22 模型文件夹，放置于项目的 pcside/voice/model/ 目录下即可。
### 3. 快速启动
在 PC 端的项目根目录，直接双击或运行高内聚启动器
```bash
python launcher.py
```
配置修改：系统首次启动后，会在根目录自动生成 config.ini。您可以直接用记事本打开它，修改端口、AI 接口或唤醒词参数。
### 4. 语音交互指南 (以唤醒词"小爱同学"为例)
常规问答："小爱同学，现在的电泳液位正常吗？"
(系统将抓取当前画面 + 检索往期知识库 -> 交由视觉大模型分析 -> TTS 语音播报解答)

快速档案记录："小爱同学，记一下，今天的试剂配比加多了2毫升。"
(系统将该句直接切入本地 RAG 数据库进行长期物理记忆。)

长篇沉浸式听写："小爱同学，记一下..." -> 系统提示 "请说" -> "实验开始... 流量正常... 我说完了。"

### 5. 边缘节点部署
将```bashpiside/pisend_receive.py```放入树莓派。
树莓派只需安装极简依赖：
```bash
pip install websockets opencv-python-headless numpy
```
运行脚本后，树莓派会自动响应 PC 端发出的 UDP 广播，无需手动配置 IP，做到即插即连.

### 6. Thanks
本项目采用 MIT 协议开源。
感谢 Ollama、Vosk、LangChain 社区提供的卓越开源底座支撑。