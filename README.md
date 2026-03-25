# NeuroLab Hub —— 基于可编排专家模型的实验室多模态智能中枢 (V1.0.1)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Windows Desktop](https://img.shields.io/badge/Delivery-Windows%20Desktop-1f6feb)](docs/product/NeuroLab_Hub_用户手册.md)
[![Raspberry Pi](https://img.shields.io/badge/Edge-Raspberry%20Pi-green)](docs/product/NeuroLab_Hub_完整手册.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

NeuroLab Hub 是面向科研实验室场景构建的分布式多模态智能系统。系统采用 `PC` 中心端与 `Raspberry Pi` 边缘节点协同架构，覆盖实验现场监控、专家模型编排、知识导入、训练工作台、语音交互、视觉闭环和实验档案沉淀。

当前 `1.0.1` 交付基线已经收敛为一条可验证、可迁移的发布路径：

1. Windows 端以轻量 `SilentDir/onedir` 形式交付。
2. `Pi` 端复制 `pi/` 目录即可启动边缘节点。
3. GUI 已验证“模型选择、知识导入、专家模型编排、专家知识导入、LLM 训练、视觉训练、标注、档案、模型配置、开始监控”。
4. `PC-Pi` 已验证单节点和 `4` 节点虚拟闭环。
5. 语音链路已从“纯文本伪造”升级为“音频文件驱动的 Pi 本地识别上行”。

## 当前推荐交付形态

当前正式推荐交付形态为：

- Windows：`NeuroLab Hub SilentDir.exe` + `_internal/` + `APP/`
- Raspberry Pi：`pi/` 目录整体复制
- 发布方式：`zip` 分发，解压即用

不再以 `onefile` 作为当前正式发布目标。原因是 `onefile` 在本项目现有运行时下稳定性不足，而 `SilentDir/onedir` 已完成完整闭环验收。

## 已验证的发布验收范围

本轮 `1.0.1` 发布前验收覆盖：

- 新机首启与轻量 `exe` 启动
- GUI 主界面与核心子窗口打开
- 模型选择与状态同步
- 公共知识导入与刷新
- 专家资产导入、专家编排、专家知识导入
- `LLM` 训练工作区创建与训练数据导入
- 视觉训练工作区创建与训练数据导入
- 标注、档案、模型配置最小交互
- `PC-Pi` 单节点语音 + 视觉闭环
- `PC-Pi` `4` 节点并发语音 + 视觉闭环

其中语音闭环使用 `wav / 16kHz / mono / PCM16` 音频文件驱动 `Pi` 端真实离线识别，再将识别文本上行至 `PC` 进行问答、专家处理和回传播报。

## 核心闭环

### 1. 语音问答闭环
1. `Pi` 端接收音频输入并完成本地离线识别。
2. 识别文本通过 WebSocket 上行到 `PC`。
3. `PC` 路由到知识问答、专家知识问答或语音调用类模型。
4. `PC` 返回文本结果。
5. `Pi` 收到文本播报命令并本地播报。

### 2. 视觉专家闭环
1. `Pi` 常态运行边缘节点。
2. `Pi` 上送关键帧或视觉事件。
3. `PC` 调度对应专家模型与知识域。
4. `PC` 返回结构化专家结果。
5. `Pi` 完成结果确认与播报。

### 3. 训练回灌闭环
1. 用户通过 GUI 导入 `LLM` 或视觉训练数据。
2. GUI 创建训练工作区并登记任务。
3. 训练产物注册进系统。
4. 产物可作为后续运行配置或知识沉淀的基础。

## Windows 端使用方式

### 1. 从发布包启动
1. 解压发布 `zip`。
2. 进入 `NeuroLab Hub SilentDir/` 目录。
3. 双击 `NeuroLab Hub SilentDir.exe`。
4. 等待启动自检结束并进入主界面。

说明：`_internal/` 与 `APP/` 都属于运行所需目录，不能单独删除或移动。

### 2. 首次启动会准备什么
首次启动会进行最小必要的运行时准备：

- Python 依赖环境检查
- Ollama 运行时检查
- GPU 算力环境检查
- 训练运行时环境检查
- 实验室知识库目录检查

当前版本不再把 `SenseVoice` 或 `Vosk` 大模型下载放在 GUI 主启动链路中，因此不会再因语音模型下载阻塞首启界面。

## Pi 端使用方式

1. 将 [`pi/`](pi) 目录复制到 Raspberry Pi。
2. 推荐在 Windows 端先完成一键接入：

- 打开 `pc/pi_one_click_setup.json`
- 至少填写：
  - `ssh.user`
  - `ssh.password`
- 双击 `pc/一键配置树莓派.cmd`

一键脚本会自动：

- 发现可接入的 Pi
- 让 Pi 连接到与当前 PC 相同的 Wi‑Fi
- 投递 `pi/` 目录
- 触发 Pi 后台自治安装
- 安装完成后自动启动 Pi 节点

3. 如果需要在 Pi 本地查看状态，可执行：

```bash
python3 pi_cli.py install-status
python3 pi_cli.py status
```

4. 如果安装完成，再执行：

```bash
bash start_pi_node.sh
```

5. 也可以使用桌面入口：`NeuroLab Hub Pi.desktop`。
6. Windows 端进入 GUI 后点击“开始监控”，系统会扫描、连接并完成闭环。

## 发布前验证结论

当前代码基线已经通过：

- 单节点 GUI 发布验收
- `4` 节点 GUI 发布验收
- 音频文件驱动语音闭环
- 视觉专家结果闭环
- 新机运行时缓存清空后的启动验证

对应报告位于：

- `release/virtual_text_voice_closed_loop_report.json`
- `release/gui_release_acceptance_single.json`
- `release/gui_release_acceptance_multi4.json`

## 当前边界

当前 `1.0.1` 已满足“发布候选”标准，但仍有明确边界：

- `Pi` 真实麦克风、真实扬声器、真实摄像头尚未接入验证
- 当前多节点通过的是虚拟 `Pi` 验证，不是实物集群联调
- 当前仓库已收敛到 `1.0.1` 基线，源码、文档和树莓派一键接入链保持一致

## 文档入口

- [文档索引](docs/README.md)
- [用户手册](docs/product/NeuroLab_Hub_用户手册.md)
- [完整手册](docs/product/NeuroLab_Hub_完整手册.md)
- [PC-Pi 测试过程手册](docs/release/NeuroLab_Hub_PC_PI_测试过程手册.md)
- [测试报告](docs/release/NeuroLab_Hub_测试报告_1.0.1.md)
