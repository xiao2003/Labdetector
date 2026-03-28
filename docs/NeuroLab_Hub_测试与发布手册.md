# NeuroLab Hub 测试与发布手册

版本：1.0.0  
适用对象：测试人员、发布人员、交付人员、工程维护人员

## 一、文档目标

本手册用于统一说明：

- 当前版本如何测试
- 当前版本如何打包与发布
- 当前版本首次启动为什么不会长时间阻塞
- 当前 Release 与安装包应如何对外说明

## 二、测试范围

当前版本重点覆盖：

- 新机首启
- GUI 核心模块主链
- 固定管家层后台准备链
- 模型选择
- 公共知识导入
- 专家资产导入与专家知识导入
- LLM 与视觉训练最小闭环
- 单节点 `PC-Pi` 闭环
- 多节点 `PC-Pi` 虚拟闭环
- 音频文件驱动的 Pi 本地识别上行
- 视觉事件 -> 专家分析 -> 结果回传 -> ACK

## 三、固定管家层运行时说明

### 3.1 资产组成

发布链固定包含：

- `llama.cpp` Windows CPU runtime
- 固定管家层运行时封装代码
- 固定模型下载清单 `pc/models/orchestrator/orchestrator_assets.json`

安装包不直接包含 GGUF 文件。GGUF 会在首次启动 GUI 显示后后台下载到可写运行时目录。

### 3.2 首次启动策略

首次启动固定顺序为：

1. GUI 先显示
2. 后台检查固定 runtime
3. 后台检查 GGUF 是否已下载
4. 若缺失则后台下载
5. 下载完成后后台预热
6. 写入运行时状态

因此当前首启要求是：

- 主界面必须先显示
- 模型下载与预热不得阻塞 GUI

### 3.3 状态语义

固定管家层状态包括：

- `not_installed`
- `downloading`
- `download_failed`
- `warming_up`
- `ready`

当固定管家层还未 `ready` 时，系统使用确定性规则链，`planner_backend=deterministic`。固定管家层就绪后，再切换到 `planner_backend=embedded_model`。

## 四、测试方法

### 4.1 代码与最小回归

推荐至少执行：

```powershell
python -m unittest   pc.testing.test_orchestrator_runtime   pc.testing.test_orchestrator_model   pc.testing.test_expert_manager_voice_routing   pc.testing.test_monitoring_speech_policy   pc.testing.test_remote_voice_routing   pi.testing.test_voice_interaction   pi.testing.test_runtime_installer   pi.testing.test_pi_config
```

### 4.2 Pi 语音闭环

无真实语音板时，使用音频文件驱动验证：

- `pi/testing/audio_replay.py`
- `pi/testing/closed_loop_bridge.py`

验证目标：

- 音频文件进入 Pi 本地识别链
- 唤醒与命令识别正确上行
- PC 统一进入 orchestrator
- 执行层模型或专家执行链正常回传
- Pi 本地播报与停止播报正常

### 4.3 视频闭环

验证目标：

- Pi 边缘事件统一进入 `orchestrator.plan_edge_event()`
- 普通提醒只写事件摘要流，不自动播报
- 强告警自动播报
- 用户主动请求时触发关键帧上传和专家分析

### 4.4 首启体验验证

正式验证要求：

1. 用安装包在干净环境安装
2. 第一次启动程序
3. 确认主界面先出现
4. 确认固定管家层模型下载/预热只在后台开始
5. 确认 GUI 可操作
6. 确认后台状态可观测

## 五、正式发布方式

### 5.1 正式交付形态

当前正式交付形态为：

- 安装包：`NeuroLab-Hub-Setup-v1.0.0.exe`
- 便携包：`NeuroLab_Hub_1.0.0.zip`
- 复验包：`NeuroLab_Hub_1.0.0_fresh_validation.zip`

正式推荐普通用户优先使用安装包。

### 5.2 GitHub Release 口径

Release 正文应明确说明：

- 安装包为正式交付形态
- 固定管家层模型采用“安装后后台下载 + 后台预热”
- 首次启动 GUI 不会因为固定模型加载而长时间阻塞
- 语音与视频闭环当前已支持软件主链验证

## 六、当前测试结论

当前 `1.0.0` 版本已经满足：

- 安装/解压可用
- GUI 主链可用
- 固定管家层运行时结构已接入发布链
- 固定管家层模型下载与预热采用后台策略
- Pi 轻前端角色明确
- 语音与视频闭环主链已收敛为统一编排入口

## 七、文档入口

- 项目总览与使用手册：[`docs/NeuroLab_Hub_项目总览与使用手册.md`](./NeuroLab_Hub_项目总览与使用手册.md)
- 版权与软著材料：[`docs/NeuroLab_Hub_版权与软著材料.md`](./NeuroLab_Hub_版权与软著材料.md)
- 文档归档索引：[`docs/archive/README.md`](./archive/README.md)
