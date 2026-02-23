# LabDetector — 面向微纳流体实验室的多模态智能视觉管理系统 / LabDetector — Multimodal Visual Management for Microfluidics Labs

简短说明（中文） | Brief summary (English)

- 本项目实现边缘（Raspberry Pi 等）与中枢（PC/工作站）协同的多模态感知与交互平台，结合视觉、语音与知识增强检索（RAG），用于实验室操作监测与风险提示。
- This project implements a distributed multimodal sensing and interaction platform (edge nodes such as Raspberry Pi + central PC), combining vision, speech, and retrieval-augmented generation (RAG) to monitor lab operations and provide risk alerts.

---

快速目视导览 / Quick at-a-glance

- 主要目录：
  - `pcside/` — PC/中枢端（推理、TTS、日志、网络）
  - `piside/` — 边缘采集端（摄像头/麦克风采集与发送）
  - `knowledge_base/` — RAG 示例/内容
  - `test/` — 环境与依赖检测脚本
- Key folders:
  - `pcside/` — central/PC side (inference, TTS, networking, logs)
  - `piside/` — edge side (capture & send)
  - `knowledge_base/` — RAG samples
  - `test/` — checks & diagnostics

---

核心目标（给老师看的要点） / Core goals (for quick review)

1. 实时感知：采集视频/音频，做手部/动作/物体的结构化判断。
2. 风险检测与告警：检测到异常或违规操作时触发语音/界面提示。
3. 可溯源的决策：利用 RAG 将模型建议与知识库证据链接，降低幻觉风险。

1. Real-time perception: capture video/audio and extract structured hand/action/object information.
2. Risk detection & alerting: voice/UI alerts on anomalies.
3. Traceable decisions: RAG links model outputs to knowledge evidence.

---

部署（Deployment） — 目标：在 Windows/PC（中枢）与 Raspberry Pi（边缘）上可复现

注意：以下步骤假设你已克隆仓库并在项目根目录下（`D:\Labdetector`）。

1) 建议的 Python 版本

- 推荐：Python 3.8 ~ 3.11（以项目中 `setup.py` 指示为准）
- Recommended: Python 3.8 — 3.11 (see `setup.py`)

2) Windows / PC（中枢）快速部署步骤

- 创建并激活虚拟环境（PowerShell）：

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

- （可选）运行项目自检脚本以获得安装建议：

```powershell
python setup.py
```

- 安装依赖（示例）：

```powershell
pip install -r requirements.txt
```

说明：如果仓库没有 `requirements.txt`，按需安装常见包，例如：numpy, opencv-python, torch（或依平台安装），requests, websocket-client, vosk (ASR 本地模型) 等。

- 运行 PC 端服务（示例）：

```powershell
python launcher.py
```

3) Raspberry Pi / 边缘节点部署（树莓派）

- 在树莓派上准备 Python3 环境并复制代码。
- 激活虚拟环境并安装依赖：

```bash
python3 -m venv .venv; source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- 启动采集发送脚本：

```bash
python3 piside/pisend.py
# 或接收/测试脚本
python3 piside/pisend_receive.py
```

4) PyTorch 与硬件加速提示

- 如果需要 GPU 加速，请按 PyTorch 官方安装页选择适合的 CUDA 版本并安装。示例（CPU/无CUDA）：

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

- On Pi, prefer CPU/mobile/lightweight models (或使用 ONNX/量化模型以节省资源）。

5) 网络与配置

- 编辑：`pcside/core/config.ini`（或 `pcside/config.txt`）设置：
  - 中央服务监听 IP/端口
  - 边缘节点 ID 与密钥（若启用认证）
  - 模型路径与语音合成参数

- 默认路径举例（配置文件片段）：

```
[network]
host = 0.0.0.0
port = 8765

[tts]
engine = local
model_path = ./models/tts-model
```

---

运行验证（Smoke test）

1. 启动 PC 端：`python pcside\main.py`，查看 `pcside/log/` 中是否产生新日志。
2. 在 Pi 端运行 `piside/pisend.py`，观察 PC 端是否接收到数据并在日志中记录。
3. 可使用 `test/check_torch.py`、`test/check_version.py` 验证环境。

---

常见问题 & 排查要点 / Troubleshooting

- 模块导入失败：确保虚拟环境已激活并安装依赖；运行 `python setup.py` 获取提示。
- 摄像头/麦克风无数据：检查设备权限、驱动、设备名称；在 Pi 上确认摄像头接口启用（raspi-config）。
- 语音/ASR 效果差：确认 ASR/TTS 模型路径和采样率，优先使用项目中的 `test/qwen/vosk-model-small-cn-0.22` 做离线 ASR 测试。

---

准备推送（你可以直接推送） / Ready to push

如果你准备将修改提交并推送至远程仓库，常用命令（PowerShell）：

```powershell
git add README.md
git commit -m "docs: bilingual README — deployment & overview"
git push origin <branch-name>
```

将 `<branch-name>` 替换为你的分支名（如 `main` 或 `master`）。

---

附：建议的后续改进（可选） / Suggested next improvements (optional)

- 在仓库根添加 `requirements.txt`（明确版本）并把常用依赖列出；
- 添加 `examples/config.example.ini` 作为模板；
- 添加 `Makefile` 或 `scripts/` 目录来统一启动命令；
- 补充演示视频或截图，便于老师快速评估成果。

---

联系方式与许可 / Contact & License

- 欢迎通过 Issue/PR 协作；合并到公共仓库前请补充 `LICENSE`（推荐 MIT/Apache-2.0）。



(本 README 侧重部署与项目概览，若你希望我：1) 生成 `requirements.txt`；2) 添加 `config.example.ini`；3) 将 README 做成中英对照并列排格式，请回复我将继续执行并把文件推送到仓库。)
