# NeuroLab Hub —— 基于可编排专家模型的实验室多模态智能中枢 (V2.6.0)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/AI_Engine-Ollama-white)](https://ollama.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

NeuroLab Hub 是专为微纳流体力学及中小型实验室打造的**分布式智能多模态管家系统**。本项目将边缘计算（树莓派节点）与高性能中心算力（如 RTX 系列显卡）相结合，支持**动态 QoS 视频并发、RAG 本地知识库、以及离线环境下的语音交互**。

系统旨在为科研人员提供实时的实验状态监控、语音辅助数据记录以及长时实验资产的智能检索服务。


### 核心特性
* **解耦的分布式架构**：
  PC 智算中枢与 Pi 边缘节点在代码层与物理层实现彻底解耦。双端拥有独立运行环境与专属工具链。树莓派端（piside）支持无外部依赖的独立部署，降低了多节点集群的扩展与维护成本。
* **可靠的日志与异常处理机制**：
  内置全局单一真相源（SSOT）版本控制与 5 步沉浸式启动预检（Pre-flight Check）。重构了程序的退出生命周期，通过软硬件中断拦截与系统级进程终止（`os._exit`），确保在正常退出或异常中断时，均能百分百触发日志归档机制，保证实验数据不丢失。
* **动态 QoS 多节点并发**：
  主控 PC 能够根据接入的树莓派数量（1~N 台）动态下发 QoS 指令，自适应调配边缘端帧率（如 5 台设备自动平分 30FPS 带宽），避免实验室无线网络拥塞，确保 PC 端稳定 30FPS 的流畅渲染。
* **基于 RAG 的长时实验记忆**：
  集成基于 FAISS 的轻量化本地向量数据库。语音录入的实验心得可自动转化为 `.txt` 文本文件并实时进行向量化入库，支持对跨时间线的实验数据进行精准的语义关联与检索。
* **边缘语音自愈中枢**：
  将 ASR（自动语音识别）能力下放至树莓派（Pi）端，支持离线的唤醒词监听、指令解析与文本回传。配套抗系统占用的“模型资产自愈管理器”，支持在断网或文件受损时自动重试与恢复。PC 端专职处理重型 RAG 检索与 AI 决策，实现“边缘感知，中心大脑”的系统架构。
* **异步非阻塞视觉推理**：
  视频流渲染与大模型推理流程实现彻底解耦。支持 Ollama 本地私有化视觉大模型（如 Llava/Qwen-VL）满载运行。通过合理的算力分配（GPU 专用于视觉推理，CPU 处理 RAG 与控制逻辑），保障系统的快速响应。

## 更新日志

* **[V2.6.1] 纳米力学气泡追踪专家重构** (2026-03-04)
  * **纳米力学专家增强**：重构 `微纳力学多模型专家`，新增毛细管气泡追踪，支持速度大小/方向、接触角、接触线钉扎与气泡分裂后双泡分别计算。
  * **专家职责分层**：纳米力学分析与实验室安全专家模型保持独立，避免安全规则与机理分析逻辑耦合。
  * **文档更新**：新增面向在线维护的专家目录梳理结构，便于直接复制到 README / Wiki。

* **[V2.6.0] 专家聚合与结构化知识库工程化升级** (2026-03-03)
  * **专家聚合增强**：新增“综合实验室安全聚合专家”，统一覆盖危化、PPE、行为与热源风险。
  * **结构化数据库构建**：新增 `structured_kb.py`（SQLite），支持 CSV/JSON/TXT/MD/XLSX 导入与关键词查询，`kb_builder` 支持 `--structured`。
  * **纳米流体模型扩展**：新增 MATLAB→Python 迁移模型集合（接触角、弯月面曲率、LK粒子速度），并封装为 `微纳流体多模型专家`。
  * **工程化规范**：统一专家自检、策略聚合、测试基线；迁移说明已整合到 README。

* **[V2.5.0] 专家体系重构与可测试化升级** (2026-03-03)
  * **专家模型重构**：统一专家接口与版本元信息，支持多策略下发、事件声明与自检。
  * **新增核心专家**：实验室危化品识别提醒专家、实验室仪器操作规范专家、实验室装备穿戴规范专家、实验室智能问答专家、微纳流体接触角分析专家。
  * **新增常用实验室专家**：火焰烟雾风险专家、液体洒漏检测专家，补齐中小型实验室高频场景。
  * **本地/联测工具**：新增 `pcside/experts/expert_testbench.py`，支持本地事件测试与 PC-Pi 协议闭环仿真。

* **[V2.4.0] 专家闭环可靠性交付版** (2026-03-03)
  * **闭环可靠性增强**：新增 `event_id` 与 `PI_EXPERT_ACK` 确认机制，PC 端可重试回传研判结论并记录审计日志（`pcside/log/expert_closed_loop.log`）。
  * **边缘事件去重**：PC 端按 `event_id` 做重复事件抑制，避免网络抖动导致重复播报。
  * **Pi 端研判缓存**：Pi 端维护最近专家结论缓存，断续网络下仍可追溯最近告警文本。
  * **知识库构建器增强**：`kb_builder` 支持 `--dry-run`、`--reset-index`、`--report`，更适合批量导入危化品目录/SOP。

* **[V2.3.4] 专家系统闭环与知识库导入增强** (2026-03-03)
  * **闭环指令增强**：PC 端收到 Pi 关键帧并完成专家研判后，会统一通过 `CMD:EXPERT_RESULT` 回传结果。Pi 端无论是否具备扬声器都会显示文字；若检测到扬声器则自动播报语音。
  * **事件协议健壮性修复**：修复 `PI_EXPERT_EVENT` 报文解析在 JSON 含冒号场景下可能失败的问题，提升跨节点稳定性。
  * **知识库构建工具**：新增 `pcside/knowledge_base/kb_builder.py`，支持将 `txt/md/csv/json/xls/xlsx` 批量导入 RAG 知识库，便于维护危化品目录与实验室 SOP 等固化知识。

* **[V2.3.3] 专家模型测试更新** (2026-03-03)
  本次更新引入了多个领域专家模型，增强了系统在特定场景下的专业分析能力。
  * **新增专家系统框架**：在 `pcside/experts/` 目录下新增多个专家模型，包括化学品安全专家（`chem_safety_expert.py`）、设备OCR专家（`equipment_ocr_expert.py`）、通用安全专家（`general_safety_expert.py`）和防护装备专家（`ppe_expert.py`）。
  * **专业领域增强**：系统现在能够针对实验室安全、设备识别和合规性检查等特定任务提供更精准的分析和建议。

* **[V2.3.0] 重大架构升级与稳定性重构** (2026-02-24)
  本次更新对系统的底层架构进行了深度重构，全面引入微服务解耦、单一真相源（SSOT）版本控制以及容灾兜底机制。
  * **彻底的分布式解耦架构**：废除全局共享的 `tools` 目录，将工具链下放至 `pcside/tools` 和 `piside/tools`。双端实现物理级解耦，`piside` 模块可独立迁移。
  * **运行兜底机制**：重写退出生命周期，通过 `try...finally` 与 `atexit` 钩子确保任何时刻退出均能保存日志；引入 `os._exit(0)` 解决底层线程残留导致的阻塞；修复 Windows 终端下输入流乱码导致的进程卡死。
  * **启动自检流程 (Launcher)**：重构根目录 `launcher.py`，增加 5 步启动自检；引入算力探针，自动探测 CUDA 环境并在纯 CPU 模式下提供降级运行建议。
  * **模型资产自愈**：新增 `model_downloader.py`，支持缺失资产自动下载；优化 Windows 环境下的文件占用冲突处理。
  * **SSOT 版本控制**：通过根目录 `VERSION` 文件实现全局版本同步，统一标准化日志前缀（`[INFO]`, `[WARN]`, `[ERROR]`）。

## 项目目录结构

```text
Labdetector
 ┣ VERSION                     --- 版本控制文件
 ┣ requirements.txt            --- 环境依赖清单
 ┣ setup.py                    --- 项目安装与打包配置
 ┣ config.ini                  --- 全局热更新配置文件
 ┣ launcher.py                 --- 全局统一启动器 (Pre-flight Check)
 ┣ pcside/                     --- PC 智算中枢端 (挂载 RTX 算力)
 ┃ ┣ main.py                   --- PC 主控核心引擎
 ┃ ┣ experts/                  --- 专家系统模块（按“安全规范/纳米流体实验”分层）
 ┃ ┃ ┣ safety/                 --- 实验室规范专家集合
 ┃ ┃ ┃ ┣ chem_safety_expert.py
 ┃ ┃ ┃ ┣ general_safety_expert.py
 ┃ ┃ ┃ ┣ ppe_expert.py
 ┃ ┃ ┃ ┣ spill_detection_expert.py
 ┃ ┃ ┃ ┣ flame_fire_expert.py
 ┃ ┃ ┃ ┣ integrated_lab_safety_expert.py
 ┃ ┃ ┃ ┗ semantic_risk_mapper.py
 ┃ ┃ ┣ nanofluidics/           --- 纳米流体实验专家集合
 ┃ ┃ ┃ ┣ microfluidic_contact_angle_expert.py
 ┃ ┃ ┃ ┣ nanofluidics_models.py
 ┃ ┃ ┃ ┗ nanofluidics_multimodel_expert.py
 ┃ ┃ ┣ equipment_ocr_expert.py --- 设备OCR专家
 ┃ ┃ ┣ lab_qa_expert.py        --- 实验室问答专家
 ┃ ┃ ┗ utils.py                --- 专家共享工具
 ┃ ┣ tools/                    --- PC端工具链
 ┃ ┃ ┣ version_manager.py      --- 全局版本号寻路接口
 ┃ ┃ ┣ model_downloader.py     --- 模型资产自愈与静默回收器
 ┃ ┃ ┣ check_gpu.py            --- GPU测试 (含 CPU 降级容错)
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
   ┣ tools/                    --- Pi端工具链
   ┃ ┣ version_manager.py      --- 全局版本号寻路接口
   ┃ ┗ model_downloader.py     --- 模型资产自愈与静默回收器
   ┗ voice/                    --- 边缘端唤醒模型储备
     ┗ model/                  --- Vosk 离线语音模型资源
```


## 专家目录与模型说明

### 1) 当前实际目录

```text
pcside/experts
 ┣ safety/
 ┃ ┣ chem_safety_expert.py
 ┃ ┣ general_safety_expert.py
 ┃ ┣ ppe_expert.py
 ┃ ┣ spill_detection_expert.py
 ┃ ┣ flame_fire_expert.py
 ┃ ┣ integrated_lab_safety_expert.py
 ┃ ┗ semantic_risk_mapper.py
 ┣ nanofluidics/
 ┃ ┣ microfluidic_contact_angle_expert.py
 ┃ ┣ nanofluidics_models.py
 ┃ ┗ nanofluidics_multimodel_expert.py
 ┣ equipment_ocr_expert.py
 ┣ lab_qa_expert.py
 ┣ expert_testbench.py
 ┗ utils.py
```

### 2) 各模型详细说明

#### A. 实验室安全规范相关模型
- `safety/chem_safety_expert.py`：危化品识别与基础合规提醒，侧重试剂容器、标签与潜在不当操作提示。
- `safety/general_safety_expert.py`：通用实验行为安全规则，覆盖常见风险动作与场景告警。
- `safety/ppe_expert.py`：个体防护装备手套、护目镜、实验服等佩戴规范检查。
- `safety/spill_detection_expert.py`：液体洒漏场景检测与应急处置提示。
- `safety/flame_fire_expert.py`：火焰/烟雾/热源风险告警，面向起火前兆与明火风险。
- `safety/integrated_lab_safety_expert.py`：安全聚合专家，将危化、PPE、行为、热源风险统一汇总输出，用于综合安全巡检事件。

#### B. 纳米力学与微纳流体机理分析模型
- `nanofluidics/microfluidic_contact_angle_expert.py`：面向微纳流体接触角监测的轻量专家，用于单项接触角事件快速判断。
- `nanofluidics/nanofluidics_models.py`：算法库，当前包含：
  - 接触角估计
  - 弯月面曲率估计
  - LK 光流粒子速度估计
  - 毛细管气泡追踪：边缘与轮廓提取、速度与方向、接触线宽度与接触角近似、钉扎疑似检测、气泡分裂识别
- `nanofluidics/nanofluidics_multimodel_expert.py`：多模型专家编排层，负责事件匹配、阈值判断、结果组织与文本输出，已与安全规范模型解耦，专注机理分析。

#### C. 其他能力模型
- `equipment_ocr_expert.py`：仪器读数/面板文字识别与操作规范辅助。
- `lab_qa_expert.py`：实验室问答专家，结合知识库完成实验问题检索式回答。

#### D. 支撑与测试
- `utils.py`：专家间共享工具函数。
- `expert_testbench.py`：专家本地联测/回归入口，用于快速验证专家加载、路由与输出链路。
- 微纳流体/纳米力学算法迁移与设计说明文档已整合在本 README。

### 3) 职责边界说明
- **安全规范模型**只负责“是否合规/是否风险”的规则告警，不承担流体机理量化计算。
- **纳米力学模型**只负责“运动、形态与界面机理”的计算与解释，不承载安全规范聚合逻辑。
- 这样可保证：规则升级与机理升级互不影响，便于独立测试、独立演进。

### 4) 专家模型即插即用接口

- 新专家只需放入 `pcside/experts/` 并继承 `BaseExpert`，系统启动时会被 `ExpertManager` 自动扫描加载。
- 无需集中注册；模块开关通过配置项 `experts.<module_name>` 控制，`1` 为启用，`0` 为禁用。
- 统一接口方法：`expert_name`、`get_edge_policy`、`match_event`、`analyze`，可选 `supported_events`、`self_check`。
- 完整接口规范与最小代码模板已整合在本 README。

即插即用流程：
1. 新建 `pcside/experts/xxx_expert.py`。
2. 继承 `BaseExpert` 并实现约定方法。
3. 可在 `config.ini` 设置 `experts.xxx_expert=1/0`。
4. 运行 `python -m pcside.experts.expert_testbench --help` 验证加载。

### 5) 五大需求对照落点
- 需求1 复杂环境采集：`piside/edge_vision/adaptive_capture.py` + `piside/pisend_receive.py` 动态调节帧率/分辨率/压缩质量与存储预算。
- 需求2 领域适配精度：`pcside/experts/nanofluidics/` 与 `pcside/experts/safety/` 分域建模，便于专项数据集与轻量微调。
- 需求3 语义转化与异常判别：`pcside/experts/safety/semantic_risk_mapper.py` + `integrated_lab_safety_expert.py` 实现语义特征到风险等级映射。
- 需求4 本地多模态语境适配：`pcside/core/expert_closed_loop.py` 与 `pcside/communication/multi_ws_manager.py` 传递结构化 `capture_metrics` 上下文。
- 需求5 多模态协同与知识积累：视觉事件、语义风险、语音播报通过专家闭环统一链路，支撑结构化沉淀。

## 关键文档整合区

### A. 五大问题梳理与改进

#### 1) 复杂环境下视觉采集适配性
**现状不足**
- Pi 端采集参数长期固定，难以应对明暗波动、遮挡与动作速度变化。
- 采集链路对帧率、分辨率、压缩质量与存储预算缺少统一优化策略。

**本次改进**
- 新增 `piside/edge_vision/adaptive_capture.py`，实现亮度、清晰度、运动强度评估与动态采集参数建议。
- 在 `piside/pisend_receive.py` 接入自适配控制：按场景动态调节预览分辨率、JPEG 质量、发送节奏，并支持存储预算约束。
- 上报事件新增 `capture_metrics`，为后端研判和质量审计提供数据依据。

#### 2) 通用检测模型实验室适配与精度提升
**现状不足**
- 通用检测结果缺少实验室领域语义层，难以区分器具、动作、流程阶段的复合语义。
- 识别结果到风险结论的链路可解释性不足。

**本次改进**
- 新增 `pcside/experts/semantic_risk_mapper.py`，将检测类别映射为可解释语义特征。
- 形成“视觉类别 -> 语义特征 -> 风险等级/原因”链路，为后续专用数据集微调与多维特征融合提供统一接口。

#### 3) 非结构化视觉到语义与异常判别
**现状不足**
- 视觉检测框和类别难以直接用于异常操作判别。
- 风险分级缺少结构化结果与原因字段。

**本次改进**
- 在 `integrated_lab_safety_expert.py` 引入语义风险映射，输出风险等级与分数。
- 对中高风险场景输出原因列表，实现可解释预警。

#### 4) 本地化多模态大模型专业语境适配
**现状不足**
- 专业术语与实验语境下的响应偏差仍依赖人工提示词。
- 缺少标准化的视觉结果入模上下文接口。

**本次改进**
- 在事件上下文中注入 `metrics` 与 `capture_metrics`，为本地多模态模型提供结构化条件输入。
- 明确专家插件接口和语义层接口，后续可直接挂接提示工程模板与参数高效微调结果。

#### 5) 视觉-语音协同与知识结构化积累
**现状不足**
- 多源数据仍偏离散，难以沉淀为可复用知识。
- 风险告警缺少统一结构字段，不利于知识库回放与统计。

**本次改进**
- 将采集质量指标与语义风险结果纳入专家链路，打通视觉采集、检测、语义判别、风险输出。
- 为后续写入结构化知识库提供统一字段基础：`capture_metrics`、`risk_level`、`risk_score`、`reasons`。

**后续建议**
- 构建实验室专用标注规范，形成器具、动作、阶段三层标签体系。
- 推进轻量化微调路线，建立离线评测基线。
- 将语义风险结果自动写入 `structured_kb.py`，形成可检索实验审计闭环。

### B. 专家模型即插即用接口完整说明

本项目专家系统采用自动发现和统一接口插件机制。

**接入方式**
- 新增专家文件到 `pcside/experts/*.py`。
- 继承 `BaseExpert` 并实现约定方法。
- `ExpertManager` 启动时自动扫描并加载，无需手工注册。

**必须实现接口**
- `expert_name`：专家显示名称。
- `get_edge_policy()`：返回边缘事件触发策略，支持 `dict` 或 `List[dict]`。
- `match_event(event_name)`：是否处理某事件。
- `analyze(frame, context)`：核心分析逻辑，返回结果字符串。

**可选实现接口**
- `expert_version`：默认 `1.0`。
- `supported_events()`：声明支持事件列表。
- `self_check()`：自检接口。

**最小示例**
```python
from typing import Dict, List
from pcside.core.base_expert import BaseExpert


class DemoExpert(BaseExpert):
    @property
    def expert_name(self) -> str:
        return "示例专家"

    @property
    def expert_version(self) -> str:
        return "1.0"

    def supported_events(self) -> List[str]:
        return ["示例事件"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "示例事件",
            "trigger_classes": ["person"],
            "condition": "any",
            "action": "full_frame",
            "cooldown": 2.0,
        }

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        return "示例专家已处理" if frame is not None else ""
```

**启用和禁用控制**
- 配置键：`experts.<module_name>`
- 值为 `0`：禁用
- 值为 `1`：启用（默认）

示例：文件名为 `my_custom_expert.py`，对应配置键 `experts.my_custom_expert`。

**开发建议**
- 建议一文件一专家，便于独立开关与追踪。
- `analyze` 仅处理当前职责，跨职责通过新增专家实现，避免耦合。
- 输出文本尽量结构化，便于前端与日志消费。

### C. NanoFluidics 与 NanoMechanics 模型说明

本系统提供常见微纳流体与纳米力学图像处理算法，支持 MATLAB 流程迁移。

**已实现模型**
1. 接触角估计 `estimate_contact_angle_from_silhouette`。
2. 粒子速度估计 `estimate_particle_velocity_lk`。
3. 弯月面曲率估计 `estimate_meniscus_curvature`。
4. 毛细管气泡追踪套件 `run_nanomechanics_bubble_suite`，支持边缘检测、速度和方向估计、接触线接触角近似、钉扎提示、单泡分裂双泡识别。

**集成入口**
- `pcside/experts/nanofluidics/nanofluidics_models.py`
- `pcside/experts/nanofluidics/nanofluidics_multimodel_expert.py`

**典型场景**
- 电渗流驱动下的毛细管气泡迁移监测。
- 电泳驱动下的气泡速度与方向在线估计。
- 分裂前后子气泡追踪与接触线稳定性诊断。

**建议扩展方向**
- Young-Laplace 曲线拟合。
- 接触线钉扎持续时间统计。
- 颗粒浓度场估计。
- Capillary number / Bond number 在线估计。

## 硬件准备与部署清单

为保障大模型推理的响应速度与多路视频流的传输稳定性，建议参考以下硬件配置：

### 1. 中心计算枢纽 (PC 端)
负责全过程的 AI 视觉推理、RAG 向量检索、语音语义解析及 GUI 交互渲染。
* **算力设备 (GPU)**：建议配置 NVIDIA RTX 3090 / 4090 / 5090 或同等具备 24GB 以上显存的计算卡（用于支撑 Ollama 多模态视觉大模型满载运行）。
* **内存 (RAM)**：建议 32GB 及以上，以保障多节点视频帧缓存与本地向量数据库的稳定运行。
* **外设交互**：需配置独立麦克风（用于唤醒交互）及音频输出设备（用于接收系统语音反馈）。
* **操作系统**：Windows 10/11 或 Ubuntu 22.04（需提前配置完善的 CUDA 驱动环境）。

### 2. 边缘监控节点 (树莓派集群)
负责实验点位的视频采集、流媒体压缩传输及本地语音响应。
* **主控板**：Raspberry Pi 4B 或 Raspberry Pi 5。
* **摄像头**：建议使用树莓派官方 CSI 摄像头模块（需兼容 `picamera2` 库）。
* **电源供应**：建议使用官方标准 Type-C 电源（15W / 27W），保障满载并发状态下的供电稳定性。

### 3. 网络环境要求
* **网络拓扑**：所有设备需处于**同一局域网（同一网段）**。
* **带宽保障**：建议部署 Wi-Fi 6 (802.11ax) 标准的千兆路由器。系统内置 QoS 动态调频机制，常规路由设备即可稳定承载 5 台以上边缘节点的并发数据流。

---

## 上手指南
### 0. 克隆项目
```bash
# 1. 克隆项目
git clone https://github.com/labdetector/Labdetector.git
cd Labdetector
# 2. 安装项目依赖 (建议在虚拟环境中执行)
pip install -e .
````

### 1. 中心端部署 (PC)
在项目**根目录**下执行以下命令，完成依赖安装与环境初始化：
```bash
pip install -e .
```
* **AI 视觉后端**：请提前安装 [Ollama](https://ollama.ai/) 运行环境，并拉取默认模型：`ollama run llava:7b-v1.5-q4_K_M`。
* **离线语音模型**：系统内置资产自愈机制，初次启动时将自动下载 Vosk 离线语音模型。若处于纯离线环境，请手动下载 `vosk-model-small-cn-0.22` 并解压至 `pcside/voice/model/`。

### 2. 边缘端部署 (Raspberry Pi)
得益于物理级解耦架构，您只需将项目中的 `piside` 文件夹整体拷贝至边缘设备，进入该目录执行环境安装即可独立运行：
```bash
cd piside
pip install -e .
```

### 3. 配置与集群同步
PC 主控程序首次启动后，将在根目录自动生成 `config.ini` 配置文件。
用户仅需在 PC 端修改该文件中的核心参数（如唤醒词、识别开关等），系统在建立连接后，会**自动将配置参数下发并同步至所有在线的边缘节点**，无需在边缘端进行重复的人工配置。

### 4. 语音交互示例
本系统支持多轮对话与长时记忆录入，基础交互指令参考如下：
1. **状态研判**："小爱同学，现在的流量正常吗？"（系统将结合实时监控画面与知识库输出分析结论）。
2. **数据存档**："小爱同学，记一下，这组样品的流动速度比昨天快了 10%。"（自动转化为文本并存入本地向量库）。
3. **连续录入**：
   > 👨‍🔬 实验员："小爱同学，记一下..."
   > 🤖 系统："好的，请讲。"
   > 👨‍🔬 实验员："...（口述长段落实验观测现象）... 我说完了。"

### 5. 知识库构建（结构化/非结构化）
支持将本地危化品目录、实验室安全操作标准等文件导入到 RAG。

```bash
# 实际导入并输出报告
python -m pcside.knowledge_base.kb_builder ./pcside/knowledge_base/docs ./my_safety_excel/ --report kb_report.json

# 仅做扫描预检
python -m pcside.knowledge_base.kb_builder ./my_safety_excel/ --dry-run

# 导入前重置向量索引
python -m pcside.knowledge_base.kb_builder ./my_safety_excel/ --reset-index

# 同步构建结构化SQLite知识库
python -m pcside.knowledge_base.kb_builder ./my_safety_excel/ --structured --report structured_report.json
```

支持格式：`txt`、`md`、`csv`、`json`、`xls`、`xlsx`。

### 6. 协议与致谢
本项目采用 **MIT** 协议开源。感谢 Ollama、Vosk 以及 LangChain 社区提供的底层技术支撑。

## 全部MD文档整合归档

以下内容为仓库内其余 Markdown 文档的整合版本，便于统一分享与查阅。


### 来源：`LAB_5_QUESTIONS_IMPROVEMENTS.md`

# 实验室智能系统五大问题梳理与改进

## 1) 复杂环境下视觉采集适配性
### 现状不足
- Pi 端采集参数长期固定，难以应对明暗波动、遮挡与动作速度变化。
- 采集链路对帧率、分辨率、压缩质量与存储预算缺少统一优化策略。

### 本次改进
- 新增 `piside/edge_vision/adaptive_capture.py`，实现亮度/清晰度/运动强度评估与动态采集参数建议。
- 在 `piside/pisend_receive.py` 接入自适配控制：按场景动态调节预览分辨率、JPEG 质量、发送节奏，并支持存储预算约束。
- 上报事件新增 `capture_metrics`，为后端研判和质量审计提供数据依据。

## 2) 通用检测模型实验室适配与精度提升
### 现状不足
- 通用检测结果缺少实验室领域语义层，难以区分“器具-动作-阶段”复合语义。
- 识别结果到风险结论的链路可解释性不足。

### 本次改进
- 新增 `pcside/experts/semantic_risk_mapper.py`，将检测类别映射为可解释语义特征。
- 形成“视觉类别 -> 语义特征 -> 风险等级/原因”链路，为后续专用数据集微调与多维特征融合提供统一接口。

## 3) 非结构化视觉到语义与异常判别
### 现状不足
- 视觉检测框和类别难以直接用于异常操作判别。
- 风险分级缺少结构化结果与原因字段。

### 本次改进
- 在 `integrated_lab_safety_expert.py` 引入语义风险映射，输出风险等级与分数。
- 对中高风险场景输出原因列表，实现可解释预警。

## 4) 本地化多模态大模型专业语境适配
### 现状不足
- 专业术语与实验语境下的响应偏差仍依赖人工提示词。
- 缺少标准化的“视觉结果入模上下文”接口。

### 本次改进
- 在事件上下文中注入 `metrics` 与 `capture_metrics`，为本地多模态模型提供结构化条件输入。
- 明确专家插件接口和语义层接口，后续可直接挂接提示工程模板与参数高效微调结果。

## 5) 视觉-语音协同与知识结构化积累
### 现状不足
- 多源数据仍偏离散，难以沉淀为可复用知识。
- 风险告警缺少统一结构字段，不利于知识库回放与统计。

### 本次改进
- 将采集质量指标与语义风险结果纳入专家链路，打通视觉采集、检测、语义判别、风险输出。
- 为后续写入结构化知识库提供统一字段基础：`capture_metrics`、`risk_level`、`risk_score`、`reasons`。

## 后续建议
- 构建实验室专用标注规范（器具、动作、阶段三层标签体系）。
- 推进轻量化微调路线（LoRA/QLoRA）并建立离线评测基线。
- 将语义风险结果自动写入 `structured_kb.py`，形成可检索的实验审计闭环。


### 来源：`pcside/experts/EXPERT_PLUGIN_INTERFACE.md`

# 专家模型即插即用接口说明

本项目的专家系统采用 **自动发现 + 统一接口** 的插件机制：
- 新增专家文件到 `pcside/experts/*.py`；
- 继承 `BaseExpert` 并实现约定方法；
- `ExpertManager` 启动时自动扫描并加载，无需手工注册。

## 1. 最小接口（必须实现）

`BaseExpert` 约束如下：
- `expert_name`：专家显示名称（唯一性建议由开发者保证）。
- `get_edge_policy()`：返回边缘事件触发策略（`dict` 或 `List[dict]`）。
- `match_event(event_name)`：是否处理某事件。
- `analyze(frame, context)`：核心分析逻辑，返回结果字符串（空字符串表示无输出）。

可选实现：
- `expert_version`：默认 `1.0`。
- `supported_events()`：声明支持事件列表，便于自检和文档化。
- `self_check()`：继承默认自检或按需覆盖。

## 2. 即插即用示例

```python
from typing import Dict, List
from pcside.core.base_expert import BaseExpert


class DemoExpert(BaseExpert):
    @property
    def expert_name(self) -> str:
        return "示例专家"

    @property
    def expert_version(self) -> str:
        return "1.0"

    def supported_events(self) -> List[str]:
        return ["示例事件"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "示例事件",
            "trigger_classes": ["person"],
            "condition": "any",
            "action": "full_frame",
            "cooldown": 2.0,
        }

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        return "示例专家已处理" if frame is not None else ""
```

## 3. 启用/禁用控制（无需改代码）

`ExpertManager` 会按模块名读取配置项：
- 配置键：`experts.<module_name>`
- 值为 `0`：禁用该专家
- 值为 `1`：启用该专家（默认）

例如，文件名为 `my_custom_expert.py`：
- 配置键为 `experts.my_custom_expert`

## 4. 开发约定建议

- 一个文件内可包含多个专家类，但建议“一文件一专家”，便于独立开关与追踪。
- `analyze` 建议仅做当前职责内判断，跨职责通过新增专家实现，避免耦合。
- 输出文本尽量结构化（指标 + 阈值 + 结论），便于前端/日志消费。


### 来源：`pcside/experts/NANOFLUIDICS_MODELS.md`

# NanoFluidics / NanoMechanics Models (MATLAB -> Python Port Notes)

本目录提供了常见微纳流体与纳米力学实验图像处理算法的 Python 版本，便于将实验室已有 MATLAB 脚本迁移到本系统。

## 已实现模型
1. **接触角估计** (`estimate_contact_angle_from_silhouette`)  
   - MATLAB 常见流程：`rgb2gray -> imgaussfilt -> edge -> bwboundaries`。
2. **粒子速度估计（Lucas-Kanade）** (`estimate_particle_velocity_lk`)  
   - MATLAB 对应：`opticalFlowLK` / `vision.PointTracker`。
3. **弯月面曲率估计** (`estimate_meniscus_curvature`)  
   - MATLAB 对应：边缘提取 + 二次曲线拟合 `polyfit`。
4. **毛细管气泡追踪套件** (`run_nanomechanics_bubble_suite`)  
   - 支持轮廓边缘检测、速度大小/方向估计、接触线接触角近似、接触线钉扎提示、单泡分裂为双泡识别。

## 集成入口
- `pcside/experts/nanofluidics/nanofluidics_models.py`
- `pcside/experts/nanofluidics/nanofluidics_multimodel_expert.py`

## 典型适配场景
- 电渗流（EOF）驱动下的毛细管气泡迁移监测
- 电泳（EP）驱动下的气泡速度与方向在线估计
- 分裂前后子气泡追踪与接触线稳定性诊断

## 建议后续扩展
- Young-Laplace 曲线拟合
- 接触线钉扎事件持续时间统计
- 颗粒浓度场估计（PIV 近似）
- Capillary number / Bond number 在线估计


### 来源：`Notebook/Pi5 SSH部署指南.md`

# 🛠️ 树莓派 5 远程开发：PyCharm 环境配置实战文档

## 1. 核心目标
建立一个**“本地编辑 -> 自动同步 -> 远程执行”**的闭环，彻底解决在不同网络环境（如手机热点、实验室 WiFi）切换开发时，IDE 路径映射混乱导致的 `/tmp/pycharm_project_xxx` 找不到文件报错问题。

---

## 2. 环境清单
* **硬件**：树莓派 5 (Alexander)
* **网络**：局域网 / 手机热点 (使用 `nmcli` 命令行注入连接)
* **IDE**：PyCharm Professional (Paid Tier)
* **解释器**：远程 Python 3.13 (位于虚拟环境 `yolo_env`)

---

## 3. 配置全流程 (避坑精华版)

### 第一步：建立 SSH 与同步映射 (Deployment)
1.  **菜单路径**：`Settings` -> `Build, Execution, Deployment` -> `Deployment`。
2.  **Connection 标签**：设置 `Root Path` 为 `/home/alexander`。
3.  **Mappings 标签**：
    * **Local Path**: `D:\Labdetector\piside`
    * **Deployment Path**: `Labdetector/piside` (注意：此相对路径会与 Root Path 自动拼接)。
4.  **关键点**：配置完成后，必须手动右键左侧项目文件夹执行 `Deployment` -> `Upload`，确保树莓派物理路径中存在该目录。

### 第二步：配置项目解释器 (Interpreter)
1.  **添加方式**：点击 PyCharm 右下角状态栏 -> `Add New Interpreter` -> `On SSH`。
2.  **路径指向**：手动填入虚拟环境 Python 路径 `/home/alexander/yolo_env/bin/python`。
3.  **底层基因修正 (彻底根除 /tmp 报错)**：
    * 若运行报错找不到文件，进入 `Show All...` 解释器列表。
    * 点击 **Path Mappings** 图标（文件夹映射图标）。
    * **删除**所有包含 `/tmp/pycharm_project_xxx` 的默认记录。
    * **手动添加**：`D:\Labdetector\piside` <==> `/home/alexander/Labdetector/piside`。

### 第三步：同步 Python 控制台 (Console)
1.  **菜单路径**：`Settings` -> `Python Console`。
2.  **纠偏**：修改其中的 `Working directory` 和 `Path mappings`，确保其与第二步的解释器映射路径完全一致。
3.  **生效**：点击控制台左侧红色方块 **⏹️** 彻底杀死旧进程并重启控制台。

---

## 4. 常见报错及排查逻辑

| 报错现象 | 根源分析 | 解决方法 |
| :--- | :--- | :--- |
| `cd: /tmp/xxx: No such file` | 解释器底层路径映射未更新或存在旧缓存 | 物理删除该解释器配置，在确保 Deployment 路径正确后重新添加 |
| `ModuleNotFoundError: pcside` | PyCharm 跨设备自动导包错误 | 删掉跨设备导入（如 `from pcside import...`），改为本地标准 `import` |
| `ModuleNotFoundError: vosk` | 远程虚拟环境缺少第三方依赖库 | 在终端执行 `/home/alexander/yolo_env/bin/pip install vosk` |

---
> **Tip**: 建议将手机热点设置为树莓派的备用 WiFi 优先级。当环境网络不可用时，开启热点即可通过 `pi5.local` 或固定 IP 快速重连。
