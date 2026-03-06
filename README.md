# LabDetector 智能实验室监控软件 (V3.0.2)

[![Windows](https://img.shields.io/badge/platform-Windows_10_11-blue.svg)](https://www.microsoft.com/windows/)
[![Python 3.11](https://img.shields.io/badge/build-Python_3.11-blue.svg)](https://www.python.org/)
[![Desktop EXE](https://img.shields.io/badge/delivery-Desktop_EXE-1f8f6f.svg)](https://github.com/xiao2003/Labdetector)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LabDetector 3.0 是一套面向实验室场景的桌面可视化监控软件。系统延续原项目“边缘采集 + 中心调度 + 专家研判 + 本地知识增强”的总体技术路线，但在交付形态上完成了从命令行原型到桌面 EXE 软件的升级：`launcher.py` 与 `pcside/main.py` 中的主要选项逻辑已收口到统一桌面界面，用户可直接双击 `LabDetector.exe` 启动软件，完成自检、配置、监控、日志查看、知识库管理和演示录屏。

从工程实现看，系统当前由 PC 智算中枢、树莓派边缘节点、专家模型编排框架、多知识库系统和桌面可视化外壳共同组成。README 当前版本在保留 2.6.2 章节结构的前提下，重新整理 3.0.2 的软件交付、专家演示、多知识库、接口边界、部署方式与测试建议，便于软著登记、版本发布和后续维护。

用户手册见：[docs/LabDetector软件说明书.md](docs/LabDetector软件说明书.md)

## 1. 核心特性

### 1.1 分布式双端协同架构
系统继续采用中心端与边缘端解耦的部署方案。PC 中心端负责统一启动、自检、专家路由、知识库检索、语音协同与可视化展示；树莓派边缘端负责摄像头采集、轻量触发、语音能力上报和事件回传。该架构既支持单机摄像头演示，也支持多节点实验位的并行监控。

### 1.2 可编排的专家模型体系
系统围绕 `BaseExpert` 与 `ExpertManager` 构建专家插件机制。各专家在目录中按模块组织，在运行时自动扫描和加载，并统一通过事件名、边缘策略、自检接口和知识库作用域参与协同。3.0.2 已纳入危化品、PPE、通用安全、明火烟雾、液体洒漏、仪器 OCR、实验问答、手部姿态、接触角和微纳多模型等专家。

### 1.3 面向实验现场的闭环通信机制
边缘节点命中特定策略后，会将事件元数据和关键帧通过统一协议回传至中心端。中心端完成专家研判后，继续以闭环报文回传结果并等待 ACK 确认。该链路已支持节点能力上报、重复事件去重、ACK 超时重试、日志审计和多节点状态独立维护，能够满足实验室现场对稳定性和可追踪性的要求。

### 1.4 本地知识增强与实验记忆能力
系统在知识侧同时提供向量检索和结构化检索两条路径。`common` 公共底座知识库用于承载制度、SOP、通用规范和实验模板；`expert.*` 专家专属知识库用于承载危化目录、设备规则、实验问答语料等专业内容。桌面端已提供“知识库管理”入口，支持按作用域导入文件或目录。

### 1.5 视觉感知、语音交互与专业分析联动
系统支持视频预览、边缘事件触发、语音唤醒、实验问答、运行日志、软件说明页和多节点监控墙联动展示。在 3.0.2 中，专家分析结果、自检过程、节点提示和日志输出被统一回收到桌面软件界面中，同时新增隐藏演示模式，便于在真实摄像头或树莓派链路建立后逐个演示专家能力。

## 2. 更新日志

* **[V3.0.2] 桌面软件化与多知识库发布版** (2026-03-07)
  * **桌面软件交付**：默认入口升级为桌面 GUI，正式用户仅需双击 `LabDetector.exe` 即可运行，不再依赖手动执行 `.py`。
  * **正式软件目录收口**：发布目录最外层仅保留一个 `LabDetector.exe`，运行依赖统一放入 `_internal` 隐藏目录。
  * **启动自检可视化**：将原 `launcher` 自检流程和输出风格迁移到桌面软件中，日志行序和提示风格与原项目保持一致。
  * **监控墙重构**：统一展示本机摄像头或多节点画面、在线状态、节点能力和最新提示信息。
  * **多知识库体系**：支持公共底座知识库和专家专属知识库并行导入、查看与管理。
  * **隐藏演示模式**：新增仅通过 `config.ini` 激活的隐藏演示开关，可在录制视频时按专家顺序轮播提示效果。
  * **文档与版权资源**：补齐图标、版本资源、README、软件说明书和版权声明，适合软著登记与正式发布。

* **[V2.6.2] README 结构重构与接口说明升级** (2026-03-06)
  * 保留作为 3.0.2 之前的文档基线版本，用于对照旧结构与原始工程说明。

## 3. 项目目录结构

### 3.1 当前仓库总览

```text
Labdetector/
├─ VERSION
├─ config.ini
├─ launcher.py
├─ README.md
├─ assets/
│  └─ branding/
│     ├─ labdetector.ico
│     └─ labdetector_logo.png
├─ docs/
│  ├─ LabDetector软件说明书.md
│  └─ 软件版权声明.md
├─ pcside/
│  ├─ app_identity.py
│  ├─ desktop_app.py
│  ├─ main.py
│  ├─ communication/
│  ├─ core/
│  ├─ experts/
│  ├─ knowledge_base/
│  │  ├─ docs/
│  │  ├─ scopes/
│  │  ├─ kb_builder.py
│  │  ├─ rag_engine.py
│  │  └─ structured_kb.py
│  ├─ tools/
│  ├─ voice/
│  └─ webui/
│     ├─ runtime.py
│     ├─ server.py
│     └─ static/
├─ piside/
├─ scripts/
│  ├─ build_desktop_exe.ps1
│  ├─ prepare_release_bundle.ps1
│  ├─ version_info.txt
│  └─ write_version_info.py
└─ release/
   └─ LabDetector-v3.0.2/
      └─ LabDetector.exe
```

### 3.2 目录职责说明
- `launcher.py`：统一启动入口，支持桌面模式、CLI 兼容模式和打包验收模式。
- `pcside/desktop_app.py`：桌面软件主界面，负责启动页、监控墙、日志区、知识库管理、关于页和说明页。
- `pcside/webui/runtime.py`：桌面端和 Web 端共用的运行时，负责自检、会话管理、节点状态、日志、监控流与隐藏演示模式。
- `pcside/core/`：系统底座层，提供配置解析、日志、专家路由、闭环协议、语音与调度能力。
- `pcside/communication/`：通信管理层，负责树莓派发现、扫描、多节点连接与回传。
- `pcside/experts/`：专家能力层，包含安全、OCR、问答、手势与微纳流体相关专家。
- `pcside/knowledge_base/`：知识增强层，提供多知识库作用域、向量检索、结构化库和导入工具。
- `pcside/tools/`：运行支撑层，提供 GPU、自检、模型资产检查等工具。
- `piside/`：边缘节点侧代码，负责采集、触发、回传和本地交互。
- `scripts/`：品牌资源、版本资源、打包和发布整理脚本。
- `docs/`：软件说明书、版权说明等正式文档。

### 3.3 运行期生成内容
- `config.ini`：统一配置文件，保存 AI 后端、模型、专家开关、网络和隐藏演示模式配置。
- `pcside/log/`：运行日志与闭环审计日志输出目录。
- `pcside/knowledge_base/structured_kb.sqlite3`：公共底座结构化知识库数据库文件。
- `pcside/knowledge_base/scopes/`：专家专属知识库作用域目录。
- `release/LabDetector-v3.0.2/`：正式发布软件目录。

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
- `chem_safety_expert.py`：面向危化品容器、标签、禁忌和处置提示的识别与提醒专家。
- `general_safety_expert.py`：面向通用安全行为场景，如实验区使用手机、分心行为等违规提醒。
- `ppe_expert.py`：面向实验服、手套、护目镜等个体防护装备合规检查。
- `spill_detection_expert.py`：面向液体洒漏识别和应急处理提示。
- `flame_fire_expert.py`：面向明火、烟雾、热源风险的告警专家。
- `equipment_operation_expert.py`：面向移液器、离心机和通用仪器操作规范检查。
- `hand_pose_expert.py`：提供手部关键点与姿态语义，用于操作动作解释和风险动作提示。
- `integrated_lab_safety_expert.py`：聚合危化、PPE、热源和行为信号，输出综合安全结论。
- `semantic_risk_mapper.py`：为综合安全分析提供结构化语义映射和风险表达能力。

### 4.3 微纳流体与纳米力学专家
- `microfluidic_contact_angle_expert.py`：面向液滴接触角的单项快速检测。
- `nanofluidics_models.py`：底层算法库，包含接触角估计、弯月面曲率、粒子速度与气泡行为分析。
- `nanofluidics_multimodel_expert.py`：微纳多模型专家，负责将多个物理量分析结果组织为综合结论。

### 4.4 其他专家与支撑模块
- `equipment_ocr_expert.py`：负责设备仪表、屏幕与局部文字的 OCR 识别。
- `lab_qa_expert.py`：负责实验室知识问答、SOP 检索和实验规则说明。
- `utils.py`：提供专家共享工具函数。
- `expert_testbench.py`：提供专家自检、本地路由测试与 PC-Pi 闭环仿真。

### 4.5 职责边界说明
系统在专家职责上采取分层设计。安全专家主要回答“是否违规”“风险等级如何”“需要什么处置动作”；OCR 与问答专家主要承担识别和知识解释；微纳流体专家主要回答“图像中的物理量如何变化”“界面形态如何解释”。这种边界划分可以降低规则逻辑、视觉识别逻辑和机理分析逻辑之间的耦合度，便于后续持续扩展。

### 4.6 新专家接入流程
1. 在 `pcside/experts/` 或其子目录下新增 Python 模块。
2. 继承 `pcside.core.base_expert.BaseExpert` 并实现核心接口。
3. 在 `config.ini` 中通过 `experts.<module_name>=1/0` 控制启停。
4. 为新专家准备 `expert.<module>` 专属知识库作用域或复用 `common` 公共知识库。
5. 使用 `python -m pcside.experts.expert_testbench --mode all` 做自检和闭环联调。

## 5. 接口详细说明

### 5.1 专家插件接口
专家插件统一继承自 `pcside/core/base_expert.py` 中定义的抽象基类，主要接口包括：
- `expert_name`：专家名称。
- `expert_version`：专家版本号。
- `supported_events()`：声明可处理的事件列表。
- `get_edge_policy()`：声明边缘触发策略。
- `match_event(event_name)`：判断事件是否由当前专家处理。
- `analyze(frame, context)`：完成核心分析并输出文本结果。
- `self_check()`：返回自检结果。
- `knowledge_scope`：声明当前专家对应的知识库作用域。

最小实现示例如下：

```python
from pcside.core.base_expert import BaseExpert

class MyExpert(BaseExpert):
    @property
    def expert_name(self) -> str:
        return "我的专家"

    def supported_events(self):
        return ["my_event"]

    def get_edge_policy(self):
        return {"event_name": "my_event", "trigger": "demo"}

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context: dict) -> str:
        return "分析完成"
```

### 5.2 边缘策略接口
边缘策略通过 `get_edge_policy()` 统一下发，策略项通常至少包含事件名、触发条件或设备类型。中心端启动多节点会话时，会自动汇总所有启用专家的边缘策略，并下发给树莓派节点执行本地触发。

### 5.3 闭环通信协议
当前专家闭环链路主要围绕以下报文：
- `PI_EXPERT_EVENT`：树莓派向 PC 上报事件、关键帧和元数据。
- `CMD:EXPERT_RESULT`：PC 向边缘节点回传专家分析结果。
- `PI_EXPERT_ACK`：边缘节点对分析结果回传 ACK。
- `PI_CAPS`：边缘节点上报麦克风、扬声器等能力信息。

3.0.2 的桌面软件会把这些协议对应的状态变化收口到监控墙卡片和日志区中展示。

### 5.4 知识库接口
知识库接口统一由 `pcside/knowledge_base/rag_engine.py` 提供，支持：
- `common` 公共底座知识库。
- `expert.<module>` 专家专属知识库。
- 文本型文件与表格型文件导入。
- 向量知识库与结构化知识库并行检索。
- 问答专家与专业专家按作用域联动检索。

### 5.5 纳米模型输出说明
微纳流体相关专家当前支持接触角、气泡行为、多模型指标等输出形式。实际输出内容取决于输入画面质量、边界清晰度和物理量可见性。3.0.2 中这类分析结果既可出现在日志中，也可在演示模式中按步骤轮播展示其预期能力范围。

## 6. 硬件准备与部署清单

### 6.1 中心计算枢纽 (PC 端)
- Windows 10/11 电脑一台。
- 摄像头一套或至少一个可用视频输入设备。
- 麦克风、扬声器可选，用于语音助手与播报功能。
- 运行目录建议直接使用 `release/LabDetector-v3.0.2/`。

### 6.2 边缘监控节点 (Raspberry Pi)
- Raspberry Pi 节点若干。
- 摄像头模组或 USB 摄像头。
- 与中心端处于可通信局域网中。
- 可选配麦克风、扬声器，用于节点能力演示。

### 6.3 网络环境要求
- 中心端与边缘节点位于同一实验室网络或可互通网段。
- 多节点模式需要保证 WebSocket 端口可通。
- 若使用云端模型，需要额外具备外网能力；纯本地演示可使用 Ollama 本地后端。

### 6.4 运行环境要求
- 构建阶段推荐 Python 3.11。
- 最终用户只运行 EXE，无需手动执行源码。
- 首次运行可能触发模型或资产检查，应保留完整发布目录。

## 7. 上手指南

### 7.1 克隆项目
```powershell
git clone git@github.com:xiao2003/Labdetector.git
cd Labdetector
```

### 7.2 安装中心端依赖
开发态调试建议使用 Python 3.11 环境，并安装项目需要的依赖。若只运行正式版 EXE，可跳过此步骤。

```powershell
python -m pip install -r requirements.txt
```

### 7.3 启动中心端
正式用户建议直接运行：

```powershell
release\LabDetector-v3.0.2\LabDetector.exe
```

开发态运行入口：

```powershell
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe D:\Labdetector\launcher.py
```

CLI 兼容模式：

```powershell
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe D:\Labdetector\launcher.py --cli
```

软件内置说明页与完整用户手册：
- 软件内查看：“帮助 -> 软件说明”
- 文档查看：`docs/LabDetector软件说明书.md`

### 7.4 启动边缘端
保持原有边缘端启动方式不变，确保树莓派端摄像头与网络配置完成后再由桌面软件进入多节点监控模式。

### 7.5 配置与集群同步
在桌面软件左侧配置区中选择 AI 后端、模型预设、运行模式和预期节点数后，点击“运行启动自检”和“启动监控”即可。多节点模式下，中心端会自动扫描节点并同步专家策略和必要配置。

### 7.6 常用交互场景
- **正式监控场景**：直接启动软件，运行自检后进入本机摄像头模式或树莓派集群模式，查看监控墙和日志提示。
- **知识库维护场景**：通过“知识库管理”导入 `common` 公共底座知识库或 `expert.*` 专家知识库。
- **软著截图库场景**：依次截取启动页、主界面、监控墙、关于页、版权页和软件说明页。
- **隐藏演示模式场景**：编辑 `config.ini` 中如下配置后重新启动软件：

```ini
[shadow_demo]
enabled = True
interval_seconds = 8
```

隐藏演示模式不会在 GUI 中显示开关。开启后，只有在摄像头会话或树莓派会话真正启动后，软件才会按专家顺序轮播提示和日志，适合录制功能演示视频。

### 7.7 知识库构建
命令行导入公共底座知识库：

```powershell
python -m pcside.knowledge_base.kb_builder --scope common D:\my_docs
```

导入专家专属知识库：

```powershell
python -m pcside.knowledge_base.kb_builder --expert safety.chem_safety_expert D:\my_chem_docs
```

图像与视频建议先转换为可检索知识再导入：
- 图片：先做 OCR、标签提取、对象识别，再生成 `txt/json/csv`。
- 视频：先做 ASR、关键帧提取、事件切片，再生成 `md/json/csv`。

### 7.8 专家联调与闭环验证
推荐优先使用专家测试台做本地验证：

```powershell
python -m pcside.experts.expert_testbench --mode all
```

该命令会执行专家自检、本地事件路由测试和 PC-Pi 闭环报文仿真，是当前验证专家链路是否畅通的首选入口。

### 7.9 协议与致谢
本项目采用 **MIT** 协议开源。感谢 Python、Tk、OpenCV、Pillow、PyInstaller、Ollama、Vosk 与 LangChain 社区提供的基础能力支持。

## 8. 测试指南

### 8.1 当前测试状态说明
截至 3.0.2，桌面主界面、知识库管理、正式发布目录、专家扫描、隐藏演示模式和 EXE 冒烟链路已经贯通；但各专家在真实实验现场的逐项专项验收仍需继续补充。因此，当前版本适合作为“可交付、可演示、可扩展”的桌面软件版本，而不是宣称所有专家都已经在所有场景下完成充分验收。

### 8.2 推荐测试顺序
建议按以下顺序测试：
1. 先运行 `python -m pcside.experts.expert_testbench --mode all`，确认专家加载、自检和闭环协议没有明显异常。
2. 再验证知识库导入与查询链路，确认 `common` 和 `expert.*` 作用域可正常建立。
3. 随后启动桌面软件并执行启动自检，检查依赖、GPU、麦克风、离线语音模型和知识库目录。
4. 最后分别验证本机摄像头模式、树莓派集群模式和隐藏演示模式。

### 8.3 关于“启动后只有图像窗口、没有明显输出提示”的说明
3.0.2 中默认用户不再面对单一图像窗口，而是使用桌面监控墙查看状态与提示。如果进入本机摄像头模式后画面正常但没有明显专家提示，通常意味着当前画面没有命中已启用专家的事件条件。这一行为在正式监控模式下是正常的；若需要录制稳定演示视频，可使用隐藏演示模式强制按专家顺序轮播能力说明。

### 8.4 当前可直接执行的测试命令
专家自检与联调：

```powershell
python -m pcside.experts.expert_testbench --mode all
```

仅执行本地路由测试：

```powershell
python -m pcside.experts.expert_testbench --mode local
```

仅执行闭环仿真测试：

```powershell
python -m pcside.experts.expert_testbench --mode joint
```

源码语法检查：

```powershell
python -m py_compile launcher.py pcside\desktop_app.py pcside\webui\runtime.py
```

正式版 EXE 冒烟测试：

```powershell
release\LabDetector-v3.0.2\LabDetector.exe --smoke-test-file D:\Labdetector\tmp\release_smoke_v302.json
```

### 8.5 建议重点观察的测试结果
- 专家是否全部被 `ExpertManager` 成功加载。
- 启动自检是否完整输出 5 项检查结果。
- 桌面监控墙是否能正确显示节点在线状态、能力标签和提示信息。
- 知识库管理页是否能正确展示 `common` 与 `expert.*` 作用域。
- 隐藏演示模式开启后，是否会在会话启动后按专家顺序轮播提示和日志。
- 软件说明页、版权页中是否已不再出现裸露的 Markdown `**` 标记。

### 8.6 当前阶段的结论表述建议
若用于答辩、阶段汇报或软著配套说明，建议将系统当前状态表述为：LabDetector 已完成从分布式原型到桌面软件形态的升级，具备正式 EXE 交付、启动自检、可视化监控、多知识库管理和专家模型编排能力；系统主体架构、专家插件机制、知识库导入链路和边缘闭环通信已经打通，并提供适合演示视频录制的隐藏演示模式；但全部专家在真实实验场景下的专项验收仍需结合具体实验环境持续推进。

