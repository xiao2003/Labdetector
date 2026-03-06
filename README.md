# LabDetector 3.0 —— 可视化实验室智能监控与多知识库专家中枢

[![Windows](https://img.shields.io/badge/platform-Windows_10_11-blue.svg)](https://www.microsoft.com/windows/)
[![Python 3.11](https://img.shields.io/badge/build-Python_3.11-blue.svg)](https://www.python.org/)
[![Desktop EXE](https://img.shields.io/badge/delivery-Desktop_EXE-1f8f6f.svg)](#6-桌面交付与运行)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LabDetector 3.0 是一套面向实验室场景的桌面可视化软件与分布式智能监控系统。系统围绕“边缘采集、中心调度、专家研判、知识增强、可视化交付”五条主线构建，支持本机摄像头模式与树莓派多节点模式，支持专家模型联动分析，支持公共底座知识库与专家专属知识库，并以正式桌面软件目录形态交付。

3.0 版本的目标不是继续扩展命令行能力，而是把原有 `launcher.py` 和 `pcside/main.py` 中的核心逻辑收口到统一桌面软件中，满足演示、交付、软著登记和后续版本化发布的需求。

## 1. V3.0 发布重点

- 正式桌面化交付：默认入口为桌面 GUI，最终用户双击 `LabDetector.exe` 即可运行，不需要手动执行 `.py`。
- 单入口正式软件目录：正式发布目录最外层仅暴露一个 `LabDetector.exe`，运行依赖统一放入隐藏 `_internal` 目录。
- 启动自检可视化：将原项目自检流程迁入桌面界面，并保持原有自检输出风格，便于对照旧版日志。
- 平铺监控墙：统一展示本机或多节点视频画面、在线状态、节点能力和最新提示信息。
- 多知识库体系：支持公共底座知识库与专家专属知识库并行管理，桌面端已提供“知识库管理”入口。
- 软著展示能力：内置启动页、关于页、版权页、软件说明页，并支持图标、版本资源、公司主体信息写入 EXE。

## 2. 核心能力

### 2.1 桌面可视化运行控制
- 提供 AI 后端选择、模型选择、自定义模型、运行模式和预期节点数配置。
- 提供启动自检、启动监控、停止监控、刷新模型等统一操作入口。
- 所有运行状态、提示信息和监控结果统一回收至桌面软件主界面。

### 2.2 监控墙与节点提示
- 本机摄像头模式下可直接展示本机画面和专家研判结果。
- 树莓派集群模式下按卡片平铺显示各节点地址、在线状态、麦克风/扬声器能力和事件提示。
- 支持节点事件回传、ACK 确认、重复事件去重和日志留痕。

### 2.3 专家模型编排
- 系统围绕 `BaseExpert` 与 `ExpertManager` 组织专家插件。
- 已覆盖危化品识别、PPE 检查、通用安全、火焰烟雾、液体洒漏、设备 OCR、实验问答、微纳流体分析等方向。
- 专家模型可按目录扩展、按配置启停，并按事件进行自动匹配与路由。

### 2.4 多知识库架构
- `common`：公共底座知识库，承载 SOP、实验制度、通用规范、实验记录模板等公共知识。
- `expert.<module>`：专家专属知识库，承载某个专家模型独有的规则、台账、危化目录、设备说明等专业知识。
- 支持 `txt`、`md`、`csv`、`json`、`xls`、`xlsx` 导入。
- 同时支持向量知识库与结构化知识库；当向量模型未及时就绪时，仍允许先完成结构化入库，不阻塞界面使用。

### 2.5 语音与知识联动
- 支持唤醒词交互、语音问答、语音记忆归档和播报反馈。
- 语音问答会优先结合公共底座知识库和实验问答专家知识库检索上下文。
- 自检中会对麦克风链路、离线语音模型资产和知识库目录进行显式检查。

## 3. 系统架构

```text
实验现场 / 摄像头 / 树莓派节点
        │
        ├─ 边缘采集与轻量检测（piside/）
        │
        └─ 事件、关键帧、能力信息上报
                 │
                 ▼
        PC 智算中枢（pcside/）
        ├─ 桌面界面与运行时（desktop_app.py / webui/runtime.py）
        ├─ 专家路由与闭环（core/ + experts/）
        ├─ 多知识库检索（knowledge_base/）
        ├─ 语音交互（voice/）
        └─ 日志、自检、版本与打包脚本（tools/ + scripts/）
                 │
                 ▼
        LabDetector 桌面可视化软件
```

## 4. 仓库结构

```text
Labdetector/
├─ VERSION
├─ config.ini
├─ launcher.py
├─ README.md
├─ assets/
│  └─ branding/
├─ docs/
├─ pcside/
│  ├─ app_identity.py
│  ├─ desktop_app.py
│  ├─ core/
│  ├─ communication/
│  ├─ experts/
│  ├─ knowledge_base/
│  │  ├─ docs/
│  │  ├─ scopes/
│  │  ├─ kb_builder.py
│  │  ├─ rag_engine.py
│  │  └─ structured_kb.py
│  ├─ voice/
│  └─ webui/
├─ piside/
├─ release/
└─ scripts/
```

目录职责概览：
- `launcher.py`：统一启动入口，支持桌面模式、CLI 兼容模式和打包验收模式。
- `pcside/desktop_app.py`：桌面主界面、启动页、帮助页、知识库管理页。
- `pcside/webui/runtime.py`：桌面与 Web 共用运行时，负责自检、会话管理、日志、监控墙数据和知识库目录查询。
- `pcside/experts/`：专家模型目录。
- `pcside/knowledge_base/`：公共底座知识库、专家知识库、向量索引和结构化知识库实现。
- `piside/`：边缘节点侧采集、检测与交互代码。
- `scripts/`：图标生成、版本资源生成、桌面 EXE 打包和发布整理脚本。

## 5. 多知识库设计与导入策略

### 5.1 作用域设计
- 公共底座知识库：`common`
- 专家知识库：`expert.<专家模块路径>`
- 典型示例：
  - `expert.safety.chem_safety_expert`
  - `expert.lab_qa_expert`
  - `expert.equipment_ocr_expert`

### 5.2 推荐分工
- `common`：实验室管理制度、SOP、应急流程、通用问答、标准操作规范。
- 危化专家库：危化品目录、MSDS 摘要、防护要求、储存规范、禁忌反应。
- 设备专家库：仪器操作规程、报警码、校准流程、维护记录。
- 问答专家库：常见问答模板、实验术语说明、实验流程说明。

### 5.3 导入入口
- 桌面端“知识库管理”窗口：适合日常导入和现场维护。
- 命令行导入：`python -m pcside.knowledge_base.kb_builder --scope common <文件或目录>`
- 专家库导入：`python -m pcside.knowledge_base.kb_builder --expert safety.chem_safety_expert <文件或目录>`

### 5.4 图片、视频如何转化为知识
图片和视频不建议直接原样入库，推荐先转成可检索的文本或结构化记录，再导入知识库。

图片建议流程：
- OCR 提取标签、铭牌、屏幕数值。
- 目标检测或人工标注提取对象类别、位置、状态。
- 输出为 `txt`、`json` 或 `csv` 后再导入。

视频建议流程：
- ASR 提取语音内容。
- 关键帧抽取后做 OCR 或图像描述。
- 事件切片，生成“时间点 - 事件 - 风险 - 建议动作”的时间线。
- 输出为 `md`、`json`、`csv` 后导入对应知识库。

推荐原则：
- 通用制度和公共流程进 `common`。
- 某个专家独享的知识进对应 `expert.*`。
- 原始图片、原始视频保留在素材库，知识库只保留可检索结果。

## 6. 桌面交付与运行

### 6.1 最终用户运行
正式交付以 `release/LabDetector-v<版本号>/` 为准。

目录约定：
- `LabDetector.exe`：唯一对外入口。
- `_internal/`：隐藏运行时依赖目录，普通用户无需手动进入。

使用要求：
- 必须保留整个发布目录，不能只拷贝单个 EXE。
- 不应运行 `build/`、`dist/` 或打包缓存中的中间 EXE。

### 6.2 开发态运行
```powershell
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe D:\Labdetector\launcher.py
```

兼容旧控制台模式：
```powershell
C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe D:\Labdetector\launcher.py --cli
```

### 6.3 打包正式桌面版
```powershell
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File D:\Labdetector\scripts\build_desktop_exe.ps1 -PythonExe C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe
```

打包后将生成：
- `release/LabDetector-v<版本号>/`
- `release/LabDetector-v<版本号>.zip`

## 7. 软著与交付建议

建议至少保留以下材料用于软著登记或成果展示：
- 启动页截图
- 主界面截图
- 知识库管理页截图
- 关于页截图
- 版权页截图
- 软件说明页截图
- 正式发布目录截图
- EXE 属性页中的版本资源截图

## 8. V3.0.0 更新日志

**[V3.0.0] 桌面软件化与多知识库版本** (2026-03-06)
- 将原有 `launcher/main` 选项逻辑整体收口为桌面可视化软件。
- 正式软件目录最外层只保留一个 `LabDetector.exe`，运行依赖隐藏到 `_internal`。
- 启动自检与日志输出迁移到桌面软件，并保持原项目原始输出风格。
- 新增公共底座知识库与专家专属知识库作用域体系。
- 新增桌面端“知识库管理”，支持按作用域导入文件或目录。
- 新增启动页、关于页、版权页、软件说明页、图标资源和版本资源写入能力。
- 优化打包流程，正式发布目录与开发缓存目录分离。

历史 2.x 版本记录请参考 Git 提交历史与既往发布分支。

## 9. 许可证

本项目当前仓库沿用 MIT License。若用于校内成果、企业内部交付或软著登记，请以正式发布说明和版权声明文件为准。
