# NeuroLab Hub 完整手册

版本：1.0.1  
适用范围：PC 中心端、Pi 边缘节点、知识库、专家模型、语音交互、训练工作台、测试交付与发布

## 1. 项目概览

NeuroLab Hub 是面向实验室场景的多模态智能中枢系统，采用 `PC` 中心端与 `Pi` 边缘节点协同架构，覆盖：

- 实验现场监控
- 危化品与 PPE 专家分析
- 语音知识问答与语音调用类模型
- 知识导入与知识增强
- `LLM` 训练与视觉训练
- 实验档案沉淀

## 2. 当前交付基线

`1.0.1` 版本的唯一推荐交付方式为：

- Windows：`SilentDir/onedir` 轻量入口包（`exe + _internal + APP`）
- Pi：`pi/` 目录整体复制
- 发布方式：`zip`

当前不以 `onefile` 作为正式发布目标。

## 3. 五层设计

系统当前按五层收敛：

1. `Pi` 启动层：一行命令或桌面入口启动边缘节点
2. `Pi` 本地能力层：语音识别、视觉事件、播报、配置同步
3. `PC-Pi` 协议层：节点发现、策略同步、事件上送、结果回传、ACK
4. `PC` 路由与专家层：问答、专家调度、知识增强、语音调用类模型
5. `GUI` 控制与展示层：模型选择、知识导入、训练、监控、档案、日志

## 4. 闭环说明

### 4.1 语音闭环

1. `Pi` 本地完成离线语音识别。
2. 识别文本通过 WebSocket 上送 `PC`。
3. `PC` 路由到知识问答、专家问答或语音调用类模型。
4. `PC` 生成文本结果并回传。
5. `Pi` 本地播报并确认回执。

### 4.2 视觉闭环

1. `Pi` 常态运行视觉策略。
2. `Pi` 上送关键帧和事件。
3. `PC` 调度危化品、PPE 等专家模型。
4. `PC` 返回结构化结果与播报文本。
5. `Pi` 完成 ACK 与播报。

### 4.3 训练回灌闭环

1. GUI 导入训练数据。
2. 创建训练工作区。
3. 执行 `LLM` 或视觉训练任务。
4. 训练产物注册并可用于后续运行。

## 5. 目录结构

重点目录如下：

```text
assets/                    静态资源
build/                     PyInstaller 构建中间产物
dist/                      发布产物目录
docs/                      文档
pc/                        PC 中心端源码
pi/                        Pi 端源码
bootstrap_entry.py         轻量引导入口
launcher.py                主程序入口
README.md                  仓库说明
VERSION                    当前版本号
```

## 6. Windows 端启动与自检

### 6.1 首次启动行为

当前 GUI 启动自检只检查与主链路直接相关的运行时：

- Python 依赖环境
- Ollama 本地模型环境
- GPU 算力环境
- 训练运行时环境
- 实验室知识库目录

### 6.2 已修复的问题

`1.0.1` 相比早期基线，已修复：

- 首次依赖安装失败
- 启动页停留过长
- 双重启动页
- 训练工作台启动空指针
- 本地代理劫持虚拟 `Pi` WebSocket
- 系统事件流底边在不同分辨率下漂移
- 离线节点数统计口径错误
- 顶部目录栏在不同分辨率下挤压

## 7. Pi 端部署

### 7.1 复制即用

将 `pi/` 目录复制到 Raspberry Pi 后，当前推荐通过 Windows 端一键配置脚本完成首轮接入：

1. 打开 `pc/pi_one_click_setup.json`
2. 至少填写：
   - `ssh.user`
   - `ssh.password`
3. 双击 `pc/一键配置树莓派.cmd`

脚本会自动发现 Pi、同步当前 PC 所在 Wi‑Fi、投递 `pi/` 代码、触发 Pi 后台自治安装，并在安装完成后自动启动边缘节点。

Pi 本地保留以下入口：

```bash
python3 pi_cli.py install-status
python3 pi_cli.py status
bash start_pi_node.sh
```

或使用桌面入口 `NeuroLab Hub Pi.desktop`。

### 7.2 当前协议

核心链路包括：

- 节点发现广播
- `CMD:SYNC_CONFIG`
- `PI_VOICE_COMMAND:<text>`
- 视觉事件上送
- `CMD:TTS:<text>`
- `CMD:EXPERT_RESULT:<json>`
- `PI_EXPERT_ACK`

## 8. GUI 功能范围

`1.0.1` 已纳入正式验收的 GUI 项包括：

- 系统自检
- 模型选择
- 公共知识导入
- 专家资产导入
- 专家模型编排
- 专家知识导入
- `LLM` 训练工作区与数据导入
- 视觉训练工作区与数据导入
- 标注面板
- 档案中心
- 模型配置
- 开始监控
- 多节点状态与事件流

## 9. 发布前验收结果

当前版本已经通过以下正式验收：

1. 音频文件驱动 `Pi` 本地识别上行闭环
2. 单节点 GUI 发布验收
3. `4` 节点 GUI 发布验收
4. 新机缓存清空后的首启验证

报告文件：

- `release/virtual_text_voice_closed_loop_report.json`
- `release/gui_release_acceptance_single.json`
- `release/gui_release_acceptance_multi4.json`

## 10. 当前边界

- 真实 Raspberry Pi 硬件链路仍需现场联调
- 当前工作区不是 `git` 仓库，无法执行真实推送
- 当前多节点结果建立在虚拟 `Pi` 测试节点之上

## 11. 交付建议

当前基线可作为 `1.0.1` 发布候选，推荐按以下方式交付：

1. 生成 `SilentDir` 轻量包
2. 压缩为 `zip`
3. 附带 `pi/` 目录
4. 附带当前用户手册、完整手册、测试过程手册和测试报告
