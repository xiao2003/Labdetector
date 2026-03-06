# NeuroLab Hub —— 基于可编排专家模型的实验室多模态智能中枢 (V2.6.2)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/AI_Engine-Ollama-white)](https://ollama.ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

NeuroLab Hub 是一个面向实验室安全巡检、微纳流体实验观测与实验过程知识化管理的分布式多模态智能系统。项目采用“边缘采集 + 中心调度 + 专家研判 + 本地知识增强”的总体技术路线，由 PC 智算中枢与 Raspberry Pi 边缘节点协同完成现场感知、事件上报、语音交互、知识检索与结果反馈。

从工程实现看，系统已形成较为清晰的层次化结构：`launcher.py` 负责中心端统一启动与自检，`pcside/` 承担专家系统、通信管理、知识库与语音交互，`piside/` 承担边缘视觉采集、轻量检测与本地交互，`Notebook/` 主要用于沉淀方案说明与实验材料。README 当前版本旨在以更正式的工程论文/项目答辩风格，对系统目标、架构组织、核心模块、接口边界、部署方式与测试现状进行系统化说明。

## 1. 核心特性

### 1.1 分布式双端协同架构
本系统采用中心端与边缘端解耦的部署方案。中心端聚焦于多节点接入、专家路由、语音服务、知识检索与综合推理；边缘端聚焦于摄像头接入、运动检测、目标触发与现场轻交互。该设计有助于在有限算力条件下实现多实验位点扩展，并降低后续节点增减、模型替换与部署维护的复杂度。

### 1.2 可编排的专家模型体系
系统围绕 `BaseExpert` 与 `ExpertManager` 构建统一的专家插件机制。各专家模型遵循一致的事件声明、边缘策略声明、分析接口与自检接口，可以按目录组织、按配置启停，并由中心端在运行时自动扫描与装载。这使得实验室安全、设备 OCR、实验问答与微纳流体分析能够在同一框架下进行模块化协同。

### 1.3 面向实验现场的闭环通信机制
边缘节点在命中特定策略后，将事件元数据与关键帧通过统一协议上报至中心端。中心端完成专家分析后再以结果报文回传，并等待边缘节点确认。该闭环机制已支持事件去重、ACK 超时重试、节点状态独立维护与审计日志记录，可满足实验室场景中对稳定性、可追踪性与结果留痕的基本要求。

### 1.4 本地知识增强与实验记忆能力
系统在知识侧同时提供向量检索与结构化检索两条路径。向量知识库适合承接实验记录、SOP、说明文档等非结构化文本资料；SQLite 结构化知识库适合承接危化品目录、设备台账与规则表格等结构化内容。二者可共同服务于实验室问答、规则提示与历史追溯等任务。

### 1.5 视觉感知、语音交互与专业分析联动
系统不仅支持视频预览与事件触发，还提供语音唤醒、实验问答、告警播报与知识记录能力。在分析层面，安全专家可以对 PPE 穿戴、危化品操作、明火烟雾、液体洒漏及仪器规范进行判断；微纳流体专家可以对接触角、弯月面曲率、粒子速度及毛细管气泡行为进行机理性分析，从而为实验场景提供更具针对性的辅助判断。

## 2. 更新日志

* **[V2.6.2] README 结构重构与接口说明升级** (2026-03-06)
  * **核心特性重构**：重写“核心特性”表述，统一为架构、专家系统、闭环通信、知识增强与多模态交互五类能力说明。
  * **目录与专家说明更新**：根据当前代码仓库实际结构，补充 `hand_pose_expert.py`、`equipment_operation_expert.py`、`core_scheduler.py`、`pcsend.py` 等现有模块说明。
  * **文档结构精简**：移除“五大需求对照落点”与“五大问题梳理与改进”两块内容，避免 README 同时承担汇报材料与工程手册导致层次混杂。
  * **接口文档重构**：将“关键文档整合区”重构为“接口详细说明”，聚焦专家插件接口、边缘策略接口、闭环协议与知识库导入说明。

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

## 3. 项目目录结构

### 3.1 当前仓库总览

```text
Labdetector/
├─ VERSION
├─ requirements.txt
├─ setup.py
├─ config.ini
├─ launcher.py
├─ README.md
├─ Notebook/
│  ├─ NanoFluidicsModels
│  ├─ Pi5 SSH部署
│  ├─ 专家模型即插即用说明
│  └─ 实验室智能系统问题梳理
├─ pcside/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ ai_backend.py
│  │  ├─ base_expert.py
│  │  ├─ config.py
│  │  ├─ core_scheduler.py
│  │  ├─ expert_closed_loop.py
│  │  ├─ expert_manager.py
│  │  ├─ logger.py
│  │  ├─ network.py
│  │  ├─ scheduler_manager.py
│  │  └─ tts.py
│  ├─ communication/
│  │  ├─ __init__.py
│  │  ├─ multi_ws_manager.py
│  │  ├─ network_discovery.py
│  │  ├─ network_scanner.py
│  │  └─ pcsend.py
│  ├─ experts/
│  │  ├─ __init__.py
│  │  ├─ equipment_ocr_expert.py
│  │  ├─ expert_testbench.py
│  │  ├─ lab_qa_expert.py
│  │  ├─ utils.py
│  │  ├─ nanofluidics/
│  │  │  ├─ __init__.py
│  │  │  ├─ microfluidic_contact_angle_expert.py
│  │  │  ├─ nanofluidics_models.py
│  │  │  └─ nanofluidics_multimodel_expert.py
│  │  └─ safety/
│  │     ├─ __init__.py
│  │     ├─ chem_safety_expert.py
│  │     ├─ equipment_operation_expert.py
│  │     ├─ flame_fire_expert.py
│  │     ├─ general_safety_expert.py
│  │     ├─ hand_pose_expert.py
│  │     ├─ integrated_lab_safety_expert.py
│  │     ├─ ppe_expert.py
│  │     ├─ semantic_risk_mapper.py
│  │     └─ spill_detection_expert.py
│  ├─ knowledge_base/
│  │  ├─ __init__.py
│  │  ├─ kb_builder.py
│  │  ├─ rag_engine.py
│  │  ├─ rag_test.py
│  │  └─ structured_kb.py
│  ├─ tools/
│  │  ├─ __init__.py
│  │  ├─ check_gpu.py
│  │  ├─ check_mic.py
│  │  ├─ model_downloader.py
│  │  ├─ push.py
│  │  └─ version_manager.py
│  └─ voice/
│     └─ voice_interaction.py
└─ piside/
   ├─ setup.py
   ├─ config.py
   ├─ pisend_receive.py
   ├─ edge_vision/
   │  ├─ adaptive_capture.py
   │  ├─ motion_detector.py
   │  └─ yolo_detector.py
   ├─ tools/
   │  ├─ __init__.py
   │  ├─ model_downloader.py
   │  ├─ VERSION
   │  └─ version_manager.py
   └─ voice/
      ├─ __init__.py
      ├─ interaction.py
      └─ recognizer.py
```

### 3.2 目录职责说明
- `launcher.py`：中心端统一启动入口，负责版本获取、启动自检、异常退出时的日志兜底与主控制流启动。
- `pcside/core/`：系统底座层，提供配置解析、日志系统、语音合成、网络基础能力、专家路由与闭环协议封装。
- `pcside/communication/`：通信管理层，负责节点发现、网络扫描、多节点 WebSocket 管理、配置同步与策略下发。
- `pcside/experts/`：专家能力层，包含安全规范专家、微纳流体专家、OCR 专家、问答专家与测试工具。
- `pcside/knowledge_base/`：知识增强层，负责向量知识库、结构化知识库与导入构建工具。
- `pcside/tools/`：运行支撑层，提供 GPU 检查、麦克风检查、模型资产下载与版本控制工具。
- `pcside/voice/`：中心端语音交互入口。
- `piside/edge_vision/`：边缘视觉感知层，负责视频采集调节、运动检测与轻量目标检测。
- `piside/voice/`：边缘端语音识别与本地交互入口。
- `Notebook/`：文档与研究资料目录，用于保留设计说明、部署记录与算法材料。

### 3.3 运行期生成内容
- `config.ini`：系统运行期间读取和维护的统一配置文件。
- `pcside/log/`：中心端运行日志与专家闭环审计日志输出目录。
- `pcside/knowledge_base/structured_kb.sqlite3`：结构化知识库数据库文件。
- `pcside/knowledge_base/faiss_index/`：向量知识库索引目录。
- `pcside/voice/model/` 与边缘端语音模型目录：在首次运行或缺失资产时自动补齐。

## 4. 专家目录与模型说明

### 4.1 当前专家目录

```text
pcside/experts/
├─ equipment_ocr_expert.py
├─ expert_testbench.py
├─ lab_qa_expert.py
├─ utils.py
├─ nanofluidics/
│  ├─ microfluidic_contact_angle_expert.py
│  ├─ nanofluidics_models.py
│  └─ nanofluidics_multimodel_expert.py
└─ safety/
   ├─ chem_safety_expert.py
   ├─ equipment_operation_expert.py
   ├─ flame_fire_expert.py
   ├─ general_safety_expert.py
   ├─ hand_pose_expert.py
   ├─ integrated_lab_safety_expert.py
   ├─ ppe_expert.py
   ├─ semantic_risk_mapper.py
   └─ spill_detection_expert.py
```

### 4.2 安全规范专家
- `chem_safety_expert.py`：面向危化品容器、标签与试剂操作场景的风险识别与提醒。
- `general_safety_expert.py`：处理通用实验室行为安全场景，如违规使用手机、烟雾与火焰迹象等。
- `ppe_expert.py`：处理实验服、手套、护目镜等个体防护装备的合规性检查。
- `spill_detection_expert.py`：处理液体洒漏识别与应急提示。
- `flame_fire_expert.py`：处理明火、烟雾、热源邻近可燃物等风险判断。
- `equipment_operation_expert.py`：处理常见实验设备的操作规范检查。
- `hand_pose_expert.py`：提供手部关键点与姿态语义，为更高层行为理解与语义风险融合提供输入。
- `integrated_lab_safety_expert.py`：作为综合安全聚合专家，对危化、PPE、热源和行为风险进行统一汇总。
- `semantic_risk_mapper.py`：作为风险语义映射辅助模块，为聚合专家提供结构化风险表达与评分支持。

### 4.3 微纳流体与纳米力学专家
- `microfluidic_contact_angle_expert.py`：面向接触角检测任务的轻量专家，适用于单项快速判断。
- `nanofluidics_models.py`：底层算法库，当前包含接触角估计、弯月面曲率估计、LK 光流粒子速度估计与毛细管气泡追踪套件。
- `nanofluidics_multimodel_expert.py`：微纳力学多模型专家，负责对多个指标进行阈值判别、文本组织与综合结论输出。

### 4.4 其他专家与支撑模块
- `equipment_ocr_expert.py`：负责仪器面板文字、读数与局部视觉文本识别。
- `lab_qa_expert.py`：负责实验室问答、知识库召回与历史实验信息查询。
- `utils.py`：提供专家间共享的公共工具函数。
- `expert_testbench.py`：提供专家系统的本地联调、自检与闭环仿真能力。

### 4.5 职责边界说明
系统在专家职责上采取分层设计。安全规范专家主要回答“是否存在违规”“是否需要警告”“风险等级如何”等规则问题；微纳流体专家主要回答“图像中物理量如何变化”“界面形态和气泡行为如何解释”等机理问题；OCR 与问答专家则作为能力补充，为规则解释、文本识别和知识查询提供支持。该边界划分有助于降低不同领域逻辑之间的耦合程度，使规则升级、算法更新与问答扩展能够相对独立地推进。

### 4.6 新专家接入流程
1. 在 `pcside/experts/` 或其子目录下新增一个 Python 模块。
2. 继承 `pcside.core.base_expert.BaseExpert` 并实现规定接口。
3. 在 `config.ini` 中通过 `experts.<module_name>=1/0` 控制启停。
4. 使用 `python -m pcside.experts.expert_testbench --mode all` 执行自检、事件路由与闭环联调验证。

## 5. 接口详细说明

### 5.1 专家插件接口
专家插件统一继承自 `pcside/core/base_expert.py` 中定义的抽象基类。其主要接口如下：
- `expert_name`：专家名称。
- `expert_version`：专家版本号，默认值为 `1.0`。
- `supported_events()`：声明可处理的事件列表。
- `get_edge_policy()`：声明边缘节点触发策略。
- `match_event(event_name)`：判断事件是否由当前专家处理。
- `analyze(frame, context)`：完成核心分析并输出文本结果。
- `self_check()`：返回自检结果，用于测试或运维巡检。

最小实现示例如下：

```python
from typing import Dict, List
from pcside.core.base_expert import BaseExpert


class DemoExpert(BaseExpert):
    @property
    def expert_name(self) -> str:
        return "示例专家"

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
        return "示例专家已处理"
```

### 5.2 边缘策略接口
中心端通过 `ExpertManager.get_aggregated_edge_policy()` 聚合全部专家的边缘触发策略，并以 `CMD:SYNC_POLICY` 的形式下发至边缘节点。当前策略字段包括：
- `event_name`：事件名称，也是中心端路由键。
- `trigger_classes`：触发该事件所需的检测类别。
- `condition`：触发条件，通常为 `any` 或 `all`。
- `action`：边缘上传动作，如 `full_frame` 或 `crop_target`。
- `cooldown`：同类事件的冷却时间，单位为秒。

### 5.3 闭环通信协议
当前系统涉及的关键报文包括：
- `PI_EXPERT_EVENT:{json}:{base64_jpeg}`：边缘节点上报专家事件与关键帧。
- `PI_YOLO_EVENT:{json}:{base64_jpeg}`：边缘节点上报 YOLO 事件。
- `CMD:SYNC_POLICY:{json}`：中心端下发聚合策略。
- `CMD:SYNC_CONFIG:{json}`：中心端同步配置，例如唤醒词。
- `CMD:SET_FPS:{value}`：中心端根据节点数量动态调节边缘采集帧率。
- `CMD:EXPERT_RESULT:{json}`：中心端回传专家研判结果。
- `PI_EXPERT_ACK:{json}`：边缘节点确认已收到研判结果。
- `PI_CAPS:{json}`：边缘节点上报麦克风、扬声器等能力信息。

闭环处理流程为：边缘触发事件并上传关键帧，中心端解析报文并按事件名路由至专家，专家生成文本结果后由 `MultiPiManager` 回传，随后等待边缘 ACK 确认；若确认超时，系统根据配置执行重试，并将过程写入审计日志。

### 5.4 知识库接口
知识库导入统一由 `pcside/knowledge_base/kb_builder.py` 提供命令行接口，主要参数包括：
- `paths`：一个或多个待导入的文件或目录路径。
- `--dry-run`：只扫描文件，不执行实际入库。
- `--reset-index`：导入前重建向量索引。
- `--report <path>`：输出 JSON 报告。
- `--structured`：同步构建 SQLite 结构化知识库。

结构化知识库当前将记录统一写入如下字段：`category`、`name`、`value`、`source`、`created_at`。这使得系统能够在保留文本原貌的同时，按关键词对危化品、设备条目、规则说明或实验记录进行快速检索。

### 5.5 纳米模型输出说明
微纳流体相关算法当前主要围绕以下字段组织输出：
- `contact_angle_deg`：接触角估计值。
- `meniscus_curvature`：弯月面曲率估计值。
- `particle_velocity_px_per_frame`：粒子速度估计值。
- `bubbles[].velocity_px_per_frame`：气泡速度。
- `bubbles[].direction_deg`：气泡运动方向。
- `bubbles[].contact_angle_deg`：气泡接触角近似值。
- `bubbles[].pinning_suspected`：是否疑似接触线钉扎。
- `bubble_split_detected`：是否检测到气泡分裂。

在输出层，`nanofluidics_multimodel_expert.py` 会将上述数值性指标转写为适合实验现场理解与播报的自然语言结论，例如接触角超阈值、弯月面曲率偏大、粒子速度偏高或气泡疑似钉扎等。

## 6. 硬件准备与部署清单

### 6.1 中心计算枢纽 (PC 端)
- GPU：建议使用 NVIDIA RTX 3090 / 4090 / 5090 或同等级 24GB 以上显存设备，以支撑视觉模型和并发推理。
- 内存：建议 32GB 及以上，以支撑多节点视频缓存、知识库与本地模型运行。
- 音频设备：建议配置独立麦克风和扬声器，以保证语音交互链路完整。
- 操作系统：建议 Windows 10/11 或 Ubuntu 22.04，并预先安装可用的驱动环境。

### 6.2 边缘监控节点 (Raspberry Pi)
- 主控板：建议 Raspberry Pi 4B 或 Raspberry Pi 5。
- 摄像头：建议使用树莓派 CSI 摄像头，以便与边缘采集链路兼容。
- 电源：建议使用稳定供电方案，以避免长时间运行时出现掉帧或异常断开。
- 本地音频：若需要边缘端播报，可选配麦克风和扬声器。

### 6.3 网络环境要求
- 所有设备应处于同一局域网内，便于节点发现、配置同步与 WebSocket 通信。
- 多节点场景建议使用稳定的千兆路由器或 Wi-Fi 6 网络环境。
- 当节点数量增加时，中心端会动态下发帧率控制命令，以平衡吞吐、推理频率与链路稳定性。

### 6.4 运行环境要求
- 根项目安装要求 Python `>=3.9`。
- Pi 端独立安装要求 Python `>=3.7`。
- 如需启用 OCR、向量检索或 Excel 导入，请保证本机已安装相关依赖，并具备所需模型资产。

## 7. 上手指南

### 7.1 克隆项目

```bash
git clone https://github.com/labdetector/Labdetector.git
cd Labdetector
```

### 7.2 安装中心端依赖

```bash
pip install -e .
```

建议在安装完成后检查以下环境：
- Ollama 是否已安装并可正常启动。
- GPU 驱动与 CUDA 环境是否可用。
- 麦克风和扬声器是否可被程序访问。

### 7.3 启动中心端

```bash
python launcher.py
```

根据当前实现，启动器会依次执行版本读取、依赖检查、GPU 检查、音频设备检查、模型资产检查与知识库目录检查，之后进入中心端主流程。

### 7.4 启动边缘端

```bash
cd piside
pip install -e .
python pisend_receive.py
```

边缘端启动后，将等待与中心端建立连接，并接收配置同步、帧率控制与专家策略下发。

### 7.5 配置与集群同步
- 根目录 `config.ini` 是当前系统的统一配置入口。
- 中心端在建立连接后，会将唤醒词与专家策略同步至边缘节点。
- 当新增、删除或关闭专家后，建议重新启动中心端，使聚合策略重新生成并下发。

### 7.6 常用交互场景
- 实验问答：例如通过知识库查询危化品防护规范或实验规则。
- 安全巡检：例如 PPE 穿戴检查、综合安全巡检、明火烟雾巡检与液体洒漏巡检。
- 微纳分析：例如接触角检测、微纳流体多模型巡检与纳米力学气泡巡检。
- 实验记录：通过语音或知识库导入实现实验过程文本化留存。

### 7.7 知识库构建
实际导入并输出报告：

```bash
python -m pcside.knowledge_base.kb_builder ./pcside/knowledge_base/docs ./my_safety_excel/ --report kb_report.json
```

仅做扫描预检：

```bash
python -m pcside.knowledge_base.kb_builder ./my_safety_excel/ --dry-run
```

导入前重置向量索引：

```bash
python -m pcside.knowledge_base.kb_builder ./my_safety_excel/ --reset-index
```

同步构建结构化 SQLite 知识库：

```bash
python -m pcside.knowledge_base.kb_builder ./my_safety_excel/ --structured --report structured_report.json
```

### 7.8 专家联调与闭环验证

```bash
python -m pcside.experts.expert_testbench --mode all
```

该命令会执行专家自检、本地事件路由测试以及 PC-Pi 闭环报文仿真，是当前验证专家链路是否正常的首选入口。

### 7.9 协议与致谢
本项目采用 **MIT** 协议开源。感谢 Ollama、Vosk 以及 LangChain 社区提供的底层能力支持。

## 8. 测试指南

### 8.1 当前测试状态说明
截至当前版本，README 中列出的专家模型已经完成目录梳理、接口统一与基本接入，但尚未对每一个专家在真实实验场景下完成系统性的逐项验证。也就是说，当前工程状态更接近“框架已贯通、部分能力可联调、整体仍需专项测试”的阶段，而不是“所有专家均已稳定验收”的阶段。该状态应在展示、答辩和后续开发中明确说明。

### 8.2 推荐测试顺序
建议按照以下顺序进行测试，而不要直接以 `launcher.py` 的视觉窗口行为作为唯一验收标准：
1. 先执行 `python -m pcside.experts.expert_testbench --mode all`，确认专家加载、自检、事件路由与闭环协议解析没有明显报错。
2. 再验证 `kb_builder.py` 与 `structured_kb.py`，确认知识库导入链路正常。
3. 随后验证 `launcher.py` 的启动自检流程，包括 GPU、麦克风、模型资产与知识库目录是否被正确识别。
4. 最后再分别验证本机摄像头模式与树莓派集群模式下的实际事件触发情况。

### 8.3 关于“启动后只有图像窗口、没有明显输出提示”的说明
根据当前实现，本机摄像头模式启动后会首先打开预览窗口，并在控制台打印“已启动本机摄像头监控，触发专家矩阵... 按 ESC 退出。”这一类启动信息。但是否会继续出现专家研判文本，取决于当前帧是否被路由到实际存在的专家事件。

从代码逻辑看，本机摄像头模式默认将帧送入事件名 `Motion_Alert` 的路由分支；而当前仓库中已声明的专家事件主要包括 `危化品识别`、`PPE穿戴检查`、`仪器操作巡检`、`综合安全巡检`、`明火烟雾巡检`、`液体洒漏巡检`、`接触角检测` 等，并没有明显看到专家声明处理 `Motion_Alert`。这意味着在当前实现下，即使图像窗口已经成功打开，也可能不会出现明显的专家输出提示。这是当前版本的一个已知行为，应视为后续联调重点，而不能直接解释为“全部专家已正常工作”。

### 8.4 当前可直接执行的测试命令
专家自检与联调：

```bash
python -m pcside.experts.expert_testbench --mode all
```

仅执行本地路由测试：

```bash
python -m pcside.experts.expert_testbench --mode local
```

仅执行闭环仿真测试：

```bash
python -m pcside.experts.expert_testbench --mode joint
```

知识库扫描预检：

```bash
python -m pcside.knowledge_base.kb_builder ./my_safety_excel/ --dry-run
```

### 8.5 建议重点观察的测试结果
- 专家是否全部被 `ExpertManager` 成功加载。
- `self_check()` 是否全部返回正常状态。
- 本地事件路由是否能对测试样例输出文本。
- 闭环报文是否能正确生成 `CMD:EXPERT_RESULT` 与 `PI_EXPERT_ACK`。
- 启动 `launcher.py` 后控制台是否出现模型选择、模式选择、语音初始化或监控启动等信息。
- 在本机摄像头模式下，是否需要将默认事件名改为已存在的专家事件，才能观察到更明显的研判结果。

### 8.6 当前阶段的结论表述建议
若用于论文、答辩或阶段汇报，建议将系统当前状态表述为：系统主体架构、专家插件框架、知识库导入机制与边缘闭环通信链路已经基本打通；但针对全部专家模型的真实场景验证尚未完成，本机摄像头模式下的默认事件路由与专家事件映射仍需进一步联调优化。因此，当前版本更适合作为“具备可扩展性的实验平台原型”进行汇报，而不是作为“所有功能均完成稳定验收”的最终交付版本。