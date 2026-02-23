| 中文（简体） | English (Quick reference) |
|---|---|
| 项目名称：LabDetector — 面向微纳流体实验室的多模态智能视觉管理系统。简介：结合边缘节点（Raspberry Pi 等）与中枢（PC/工作站），融合视觉、语音与知识增强检索（RAG），用于实验室操作监测与风险提示。 | Project: LabDetector — Multimodal Visual Management for Microfluidics Labs. Summary: A distributed edge+central platform combining vision, speech, and retrieval-augmented generation (RAG) to monitor lab operations and provide risk alerts. |
| 主要目录（要点） | Key folders (high level) |
| - `pcside/`：PC/中枢端（推理、TTS、网络、日志）<br>- `piside/`：边缘采集端（摄像头/麦克风采集与发送）<br>- `knowledge_base/`：RAG 示例/知识内容<br>- `test/`：环境与依赖检测脚本 | - `pcside/`: central/PC side (inference, TTS, networking, logs)<br>- `piside/`: edge side (capture & send)<br>- `knowledge_base/`: RAG samples<br>- `test/`: checks & diagnostics |
| 核心目标（给评审/导师） | Core goals (for reviewers) |
| 1. 实时感知：视频/音频采集并提取手部/动作/物体等结构化信息。<br>2. 风险检测：异常或违规时触发语音/界面告警。<br>3. 可溯源决策：RAG 将模型输出与知识库证据关联，降低幻觉风险。 | 1. Real-time perception: capture video/audio and extract structured hand/action/object data.<br>2. Risk detection & alerting: voice/UI alarms on anomalies.<br>3. Traceable decisions: RAG links outputs to knowledge evidence to reduce hallucinations. |
| 部署摘要（Deployment summary） | Deployment summary |
| 先决条件：Python 3.8–3.11，虚拟环境。Windows（PowerShell）或 Raspberry Pi（Raspbian / Raspberry Pi OS）。 | Prereqs: Python 3.8–3.11, virtualenv. Deploy targets: Windows (PowerShell) or Raspberry Pi (Raspbian). |
| Windows / PC（中枢）快速步骤 | Windows / PC quick steps |
| ```powershell
# 在项目根（例如 D:\Labdetector）
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python launcher.py   # 或 python pcside\main.py
``` | ```powershell
# At project root (e.g. D:\Labdetector)
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python launcher.py   # or python pcside\main.py
``` |
| Raspberry Pi（边缘）快速步骤 | Raspberry Pi (edge) quick steps |
| ```bash
python3 -m venv .venv; source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python3 piside/pisend.py
``` | ```bash
python3 -m venv .venv; source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python3 piside/pisend.py
``` |
| PyTorch / 硬件加速提示 | PyTorch / acceleration notes |
| - 在有 NVIDIA GPU 的 PC 上，请参照 PyTorch 官网选择合适 CUDA 版本安装。<br>- 树莓派上应使用轻量/量化模型或 ONNX 运行时。 | - On GPU machines, install PyTorch with the appropriate CUDA wheel from pytorch.org.<br>- On Pi, prefer lightweight/quantized models or ONNX runtime. |
| 配置说明（示例位置） | Configuration hints (example files) |
| 推荐复制 `examples/config.example.ini` 到 `pcside/core/config.ini` 并按需修改。主要字段：网络监听（host/port）、边缘节点 ID / token、模型路径、TTS 设置、日志路径。 | Copy `examples/config.example.ini` to `pcside/core/config.ini` and edit. Key fields: network host/port, node ID/token, model paths, TTS settings, logging path. |
| 运行验证（Smoke test） | Smoke tests |
| 1. 启动 PC 端：`python launcher.py` 或 `python pcside\main.py`，检查 `pcside/log/` 是否产生日志。<br>2. 在 Pi 端运行 `python3 piside/pisend.py`，观察 PC 是否接收到数据。<br>3. 使用 `test/check_torch.py`、`test/check_version.py` 检查环境。 | 1. Start PC: `python launcher.py` or `python pcside\main.py`, check `pcside/log/` for entries.<br>2. On Pi run `python3 piside/pisend.py` and verify PC receives data.<br>3. Use `test/check_torch.py`, `test/check_version.py` to validate environment. |
| 常见问题与排查要点 | Troubleshooting highlights |
| - 模块导入失败：确认激活虚拟环境并安装依赖。<br>- 摄像头/麦克风无数据：检查设备权限/驱动；Pi 上启用摄像头接口。<br>- 语音/ASR 表现差：确认模型路径和采样率，优先使用 `test/qwen/vosk-model-small-cn-0.22` 做离线 ASR 测试。 | - Import errors: ensure venv activated and deps installed.<br>- No camera/mic data: check device permissions/drivers; enable camera interface on Pi.<br>- Poor ASR/TTS: verify model paths and sample rates; test with `test/qwen/vosk-model-small-cn-0.22`. |
| 已添加的辅助文件 | Added helper files |
| - `requirements.txt`（位于仓库根）: 包括基础依赖与常用可选项（torch, vosk, pyaudio 等）。<br>- `examples/config.example.ini`：最小配置示例，复制后修改。 | - `requirements.txt` at repository root: base deps + common optional packages (torch, vosk, pyaudio, etc.).<br>- `examples/config.example.ini`: example config file; copy and adapt to `pcside/core/config.ini`. |
| 推送（你将手动推送） | Push (you will push manually) |
| 请在本地检查修改后运行：<br>```powershell
git add README.md requirements.txt examples/config.example.ini
git commit -m "docs: bilingual side-by-side README; add requirements and config example"
# 然后推送到你的分支：
git push origin <branch-name>
``` | Run locally to commit and push changes:<br>```powershell
git add README.md requirements.txt examples/config.example.ini
git commit -m "docs: bilingual side-by-side README; add requirements and config example"
# then push to your branch:
git push origin <branch-name>
``` |
| 进一步建议 | Next improvements |
| - 添加 `LICENSE`（例如 MIT）并固定 `requirements.txt` 的版本；<br>- 提供 `config.example.ini` 的更多注释示例或常见部署脚本（PowerShell / bash）；<br>- 若需要，我可生成左右并排的 PDF 或演示截图方便提交评审。 | - Add a `LICENSE` (e.g., MIT) and pin versions in `requirements.txt`.<br>- Provide more commented `config.example.ini` or deployment scripts (PowerShell / bash).<br>- I can generate a side-by-side PDF or screenshots for your review if needed. |



*说明：我已在仓库中创建/更新 `requirements.txt` 与 `examples/config.example.ini`（如果你想我也可以按需把 `examples/config.example.ini` 覆盖到 `pcside/core/config.ini`）。你后续只需在本地运行上面的 git 命令把修改推送到远端。*
