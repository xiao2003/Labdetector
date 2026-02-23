# LabDetector：智能多模态实验室管家 (V2.3.0)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/AI_Engine-Ollama-white)](https://ollama.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LabDetector 是专为微纳流体力学及重型科研实验室打造的**分布式智能多模态管家系统**。它将边缘计算（树莓派节点）与高性能中心算力（RTX 5090）相结合，支持**动态 QoS 视频并发、RAG 私有知识库、以及完全断网环境下的离线语音交互**。

它不仅是一个监控系统，更是陪伴你进行科学研究、沉淀实验资产的 AI 师兄。


### 核心特性

* **解耦的分布式架构**：
  PC 智算中枢与 Pi 边缘节点在代码层与物理层实现彻底解耦。双端拥有独立运行环境与专属工具链。树莓派端（piside）支持无外部依赖的独立部署，极大降低了多节点集群的扩展与维护成本。
* **可靠的日志与异常处理机制**：
  内置全局单一真相源（SSOT）版本控制与 5 步沉浸式启动预检（Pre-flight Check）。重构了程序的退出生命周期，通过软硬件中断拦截与系统级进程终止（`os._exit`），确保在正常退出或异常中断时，均能百分百触发日志归档机制，保证实验数据绝不丢失。
* **动态 QoS 多节点并发**：
  主控 PC 能够根据接入的树莓派数量（1~N 台）动态下发 QoS 指令，自适应调配边缘端帧率（如 5 台设备自动平分 30FPS 带宽），避免实验室无线网络拥塞，确保 PC 端稳定 30FPS 的流畅渲染。
* **基于 RAG 的长时实验记忆**：
  集成基于 FAISS 的轻量化本地向量数据库。语音录入的实验心得可自动转化为 `.txt` 文本文件并实时进行向量化入库，支持对跨时间线的实验数据进行精准的语义关联与检索。
* **边缘语音自愈中枢**：
  将 ASR（自动语音识别）能力下放至树莓派（Pi）端，支持离线的唤醒词监听、指令解析与文本回传。配套抗系统占用的“模型资产自愈管理器”，支持在断网或文件受损时自动重试与恢复。PC 端专职处理重型 RAG 检索与 AI 决策，实现“边缘感知，中心大脑”的系统架构。
* **异步非阻塞视觉推理**：
  视频流渲染与大模型推理流程实现彻底解耦。支持 Ollama 本地私有化视觉大模型（如 Llava/Qwen-VL）满载运行。通过合理的算力分配（GPU 专用于视觉推理，CPU 处理 RAG 与控制逻辑），保障系统的快速响应。

## 更新日志
[V2.3.0] 重大架构升级与稳定性重构

日期: 2026-02-24

本次更新对系统的底层架构进行了深度重构，全面引入了微服务解耦、单一真相源（SSOT）版本控制以及工业级容灾兜底机制。系统稳定性与跨平台部署能力得到史诗级跃升。
核心更新亮点

1. 彻底的分布式解耦架构 (Decoupled Deployment)
    节点自治化：废除全局共享的 tools 目录，将工具链分别下放至 pcside/tools 和 piside/tools。现在，树莓派端（Pi）和 PC 算力端（PC）实现了真正的物理级解耦。只需将 piside 文件夹单独拷入 U 盘即可开箱即用，不再受限于项目根目录的依赖树。
2. 🛡“黑匣子”级运行兜底机制 (Bulletproof Logging)
    全天候日志归档：重写了程序的退出生命周期。通过结合 try...finally 拦截与 atexit.register 钩子，实现了无论用户在任何时刻正常退出（输入 exit/q）还是被动触发硬中断（Ctrl+C），系统都能 100% 触发兜底机制，将实验日志安全保存至本地硬盘。
    消除幽灵死锁：放弃了容易导致死锁的“绅士退出”，引入 os._exit(0) 瞬间斩断 PyTorch / FAISS 底层产生的 C++ 僵尸线程池，实现了程序的“秒级顺滑退出”。
    修复 I/O 卡死：移除了早期因防御乱码而遗留的 sys.stdin 底层流劫持代码，彻底解决了 Windows 控制台下 input() 输入无效、回车键被吞噬的恶性卡死 Bug。

3. 工业级 Pre-flight 启动自检 (Launcher)
    全局启动引擎重构：重构了根目录的 launcher.py，统一收口所有自检流程。现在启动系统会依次展示 [1/5] 到 [5/5] 的沉浸式自检进度条。
    依赖与算力探针：基于 pkg_resources 实现毫秒级依赖清单对比；自动探测当前 PyTorch 是否支持 CUDA 加速，若检测到纯 CPU 版本，会优雅降级并提供重装修复建议，告别闪退。
    RAG 引擎平滑加载：为耗时较长的 HuggingFace 向量模型初始化添加了友好的进度提示，消除“假死”错觉。

4. 模型资产自愈管理器 (Self-Healing Downloader)
    引入了独立的 model_downloader.py。当检测到缺失 Vosk 语音模型等离线资产时，系统会自动触发断点下载与部署。
    抗 Windows 占用优化：独创了“异步推迟清理”机制，完美化解了因 Windows Defender（杀毒软件）扫描文件而导致的 WinError 32 文件占用崩溃问题，并在下一次系统启动时静默回收僵尸文件。

5. 🏷单一真相源版本控制 (SSOT Versioning)
    引入根目录唯一的 VERSION 纯文本文件，配合全新编写的 version_manager.py 智能寻路接口。只需修改一次文件，全局（包括打包工具、双端启动器、主界面UI）的版本号均会自动同步，彻底消灭硬编码。
    全面弃用控制台 Emoji，统一对齐标准的 Syslog 日志前缀（[INFO], [WARN], [ERROR]），更利于后期的自动化日志分析与检索。

## 项目目录结构

系统采用了高内聚、低耦合的模块化设计，完美分离了底层通信、视觉 AI、语音交互与 RAG 引擎。

```text
Labdetector
 ┣ VERSION                     --- [新增] 全局单一真相源版本控制文件
 ┣ requirements.txt            --- 环境依赖清单
 ┣ setup.py                    --- 项目安装与打包配置
 ┣ config.ini                  --- 全局热更新配置文件
 ┣ launcher.py                 --- [重构] 全局统一启动器 (Pre-flight Check)
 ┣ pcside/                     --- PC 智算中枢端 (挂载 RTX 算力)
 ┃ ┣ main.py                   --- PC 主控核心引擎
 ┃ ┣ tools/                    --- [解耦] PC端专属工具链
 ┃ ┃ ┣ version_manager.py      --- 全局版本号寻路接口
 ┃ ┃ ┣ model_downloader.py     --- 模型资产自愈与静默回收器
 ┃ ┃ ┣ check_gpu.py            --- 算力探针 (含 CPU 降级容错)
 ┃ ┃ ┗ check_mic.py            --- 音频硬件自检
 ┃ ┣ core/                     --- 核心驱动底座
 ┃ ┃ ┣ config.py               --- 配置文件解析器
 ┃ ┃ ┣ logger.py               --- 全局日志系统
 ┃ ┃ ┣ tts.py                  --- 语音合成模块
 ┃ ┃ ┣ ai_backend.py           --- 大模型视觉推理后端 (Ollama/Qwen)
 ┃ ┃ ┗ network.py              --- 网络基础工具
 ┃ ┣ communication/            --- 通信与集群管理模块
 ┃ ┃ ┣ network_scanner.py      --- 局域网拓扑扫描器
 ┃ ┃ ┗ multi_ws_manager.py     --- 多节点 WebSocket 集群管理器
 ┃ ┣ knowledge_base/           --- RAG 知识库系统
 ┃ ┃ ┣ rag_engine.py           --- RAG 核心引擎 (text2vec + FAISS)
 ┃ ┃ ┣ faiss_index/            --- FAISS 向量数据库持久化目录
 ┃ ┃ ┗ docs/                   --- 语音记忆的 TXT 物理存档
 ┃ ┣ voice/                    --- 语音唤醒与交互中枢
 ┃ ┃ ┣ voice_interaction.py    --- 语音交互核心逻辑
 ┃ ┃ ┗ model/                  --- Vosk 离线语音模型资源
 ┃ ┗ log/                      --- 实验运行日志归档目录
 ┗ piside/                     --- Pi 边缘节点端 (高度内聚，独立运行)
   ┣ pisend_receive.py         --- Pi 边缘节点端主控流
   ┣ tools/                    --- [解耦] Pi端专属工具链
   ┃ ┣ version_manager.py
   ┃ ┗ model_downloader.py
   ┗ voice/                    --- 边缘端唤醒模型储备
     ┗ model/                  --- Vosk 离线语音模型资源
```
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
### 1. 中心端 (PC)
在项目**根目录**执行以下命令，完成环境初始化与模块注册：
```bash
pip install -e .
```
AI 后端：请安装 Ollama 并拉取视觉模型：ollama run llava:7b-v1.5-q4_K_M
离线语音：下载 vosk-model-small-cn-0.22 并放置于 pcside/voice/model/。
### 2. 边缘端 (Raspberry Pi)
将```piside```文件夹拷贝至树莓派，执行：
```bash
cd piside && pip install -e .
```
### 3. 配置同步
系统首次启动后，会在根目录自动生成```bash config.ini```文件，用于配置系统参数。请将此文件上传至所有树莓派节点，并确保其内容一致。

在```PC```端的```config.ini```中，您可以直接修改其中的唤醒词、识别开关等，主程序启动后会自动同步至所有在线的树莓派节点。

### 4. 交互指南与展望
1. **唤醒指令**："小爱同学，现在的流量正常吗？"（AI 将结合实时画面与知识库回答）
2. **知识存档**："小爱同学，记一下，这组样品的流动速度比昨天快了 10%。"
3. **连续录音**："小爱同学，记一下..." -> "好的，请讲" -> "...我说完了。"

### 5. Thanks
本项目采用 MIT 协议开源。感谢 Ollama、Vosk、LangChain 社区提供的开源底座支撑。