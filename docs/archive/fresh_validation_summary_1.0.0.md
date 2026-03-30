# NeuroLab Hub 1.0.0 新安装链路正式复验总结

## 目标

基于当前正式安装链路，完成从安装包到 `PC-Pi` 语音/视频闭环结束的一轮正式复验，覆盖：

- 安装包交付
- 首次启动与运行时状态
- 6 层架构关键能力
- 专家能力驱动调度
- 应用内自治关键场景
- Ollama 模型选择页默认候选

## 当前正式架构

当前版本按 6 层主链收敛：

1. 交互与展示层
2. 会话与运行时层
3. 管家编排层
4. 执行与知识层
5. 通信与节点管理层
6. Pi 轻前端边缘层

固定管家层采用：

- `Qwen2.5-1.5B-Instruct`
- 内置 `llama.cpp` Windows CPU runtime
- 首次启动后台下载固定 GGUF
- 就绪前 `planner_backend=deterministic`
- 就绪后 `planner_backend=embedded_model`

## 本轮正式复验范围

### 1. 安装包交付层

- 正式安装包：`D:\NeuroLab\release\NeuroLab-Hub-Setup-v1.0.0.exe`
- 安装器可正常安装
- 安装后主程序入口存在
- 安装目录内存在固定管家层 runtime 与模型资产清单

### 2. 首次启动与运行时层

已验证：

- GUI 先显示
- 固定管家层模型下载与预热只在后台执行
- 后台状态可观测
- 首启期间 GUI 可操作

对应报告：

- `D:\NeuroLab\release\smoke_install_formal_acceptance_20260329.json`

补充管理员态真实安装验证报告：

- `D:\NeuroLab\release\smoke_install_formal_acceptance_admin_20260329_r8.json`

管理员态补充结论：

- 安装器退出码 `0`
- 安装目录内主程序存在
- 首启成功拉起后台 `pythonw`
- 本地运行时状态文件写为：
  - `status = download_failed`
  - `planner_backend = deterministic`
- 失败原因记录为固定模型后台下载触发 SSL EOF

这说明：

- 安装链与 GUI 首启链路本身是通的
- 固定管家层后台准备链已经被触发
- 当前环境下模型下载失败时，系统会按正式设计回退到规则链
- GUI 不会因为固定模型下载失败而卡死或不可用

### 3. 语音闭环

已验证完整链路：

1. Pi 音频文件注入
2. Pi 本地识别生成文本
3. 文本上行到 PC
4. PC 进入 `orchestrator.plan_voice_command()`
5. 管家层按专家元数据、知识域与上下文分发
6. 结果回传 Pi
7. Pi 完成播报

对应报告：

- `D:\NeuroLab\release\formal_acceptance_virtual_closed_loop_20260329.json`

本轮已覆盖：

- 系统状态查询
- 风险分析问答
- 普通问答
- 结果播报

### 4. 视频闭环

已验证完整链路：

1. 虚拟 Pi 边缘事件上行
2. `PI_EXPERT_EVENT` / `PI_YOLO_EVENT` 统一进入 `orchestrator.plan_edge_event()`
3. PC 调度专家执行与播报策略
4. 结果回传
5. Pi 侧 ACK 正常

对应报告：

- `D:\NeuroLab\release\gui_full_closed_loop_20260329.json`
- `D:\NeuroLab\release\gui_release_acceptance_20260329.json`

本轮已覆盖：

- PPE 普通提醒
- 危化品高优事件
- 专家结果回传
- ACK
- 普通事件静默策略

### 5. GUI 与应用内自治

已验证：

- GUI 页面可打开与切换
- 事件流支持 `全部 / 告警 / 调度 / 系统` 四类筛选
- 管家自治动作会在事件流中留下可视化痕迹
- 知识库、专家中心、训练中心、档案中心均可进入
- 监控可开始/停止
- 管家层可驱动应用内动作，不越出应用边界
- 不会自动修改持久配置、不自动训练、不自动导入

### 6. 专家能力驱动调度

本轮正式口径不再接受“固定场景 -> 固定专家”的硬编码主链。

已验证当前调度依据为：

- 专家注册表元数据
- 专家知识域是否可用
- 输入类型
- 当前上下文

并确认：

- `lab_qa_expert` 可参与全局问答链
- 专家知识域作为增强层使用
- 新专家可通过补齐能力元数据进入候选，而不是修改核心场景映射

### 7. Ollama 模型选择页

已确认 GUI 中 Ollama 内置候选显示：

- `qwen3.5:4b`
- `qwen3.5:9b`
- `qwen3.5:27b`
- `qwen3.5:35b`

该项已在 GUI 完整闭环与 GUI 发布验收中实际断言。

## 本轮新增关键验证证据

- `D:\NeuroLab\release\gui_full_closed_loop_20260329_r4_gitsync.json`
- `D:\NeuroLab\_github_sync\release\virtual_text_voice_closed_loop_report.json`
- `D:\NeuroLab\_github_sync\release\gui_release_acceptance_report.json`
- `D:\NeuroLab\release\smoke_install_formal_acceptance_admin_20260329.json`

这些报告共同覆盖了：

- 首屏状态三态没有破坏 GUI 主链
- 事件流筛选、高优事件卡片和自治痕迹未破坏 GUI 主链
- `PC-Pi` 语音闭环继续成立
- `PC-Pi` 视频闭环继续成立
- GUI 发布验收与 Ollama 默认候选校验继续通过

## 正式总控验收入口

当前正式验收入口已收敛为：

- `pc/testing/formal_acceptance_suite.py`

它会按固定顺序统一串联：

1. 结构与 Pi 边缘回归
2. GUI 发布验收
3. GUI 全闭环
4. `PC-Pi` 语音/视频闭环
5. 安装首启 smoke
6. 人工 GUI 观感验收
7. 汇总报告与 fresh validation 产物生成

本地已验证总控脚本可在以下模式下跑通并产出：

- `--skip-installer-smoke`
- `--allow-manual-pending`

对应产物目录示例：

- `release/formal_acceptance_suite_smoke/`

## 本轮实际执行的关键验证

### 单元与结构回归

已重跑并通过的关键模块包括：

- `pc.testing.test_desktop_model_recommendations`
- `pc.testing.test_ollama_model_catalog`
- `pc.testing.test_orchestrator_model`
- `pc.testing.test_remote_voice_routing`
- `pc.testing.test_expert_capability_facts`
- `pc.testing.test_monitoring_speech_policy`
- `pc.testing.test_expert_manager_voice_routing`
- `pi.testing.test_voice_interaction`
- `pi.testing.test_runtime_installer`
- `pi.testing.test_pi_config`

### 集成与正式验收链

已重跑并通过：

- `pc.testing.virtual_text_voice_closed_loop_test`
- `pc.testing.gui_full_closed_loop_test`
- `pc.testing.gui_release_acceptance_test`
- `pc.testing.installer_first_launch_smoke`

本轮 UI 产品化收口也已纳入正式验收：

- 首屏状态统一为：
  - `系统已可用`
  - `后台准备中`
  - `后台准备失败（已回退规则链）`
- 事件流顶部增加“最新高优事件”常驻摘要卡片
- 自治动作日志统一为“动作 -> 结果”格式
- 知识导入反馈改为作用域 / 新增文档 / 最近一次导入时间的业务结果展示

## 当前正式结论

基于当前新安装链路，`NeuroLab Hub 1.0.0` 已完成一轮从安装包到 `PC-Pi` 语音/视频闭环结束的正式复验：

- 安装包可安装
- 首次启动 GUI 不因固定模型阻塞
- 固定管家层后台准备链可观测
- 当前环境下模型下载失败时，错误路径与规则链回退行为可观测
- 首屏状态、事件卡片和知识导入反馈均符合产品化口径
- `PC-Pi` 语音闭环通过
- `PC-Pi` 视频闭环通过
- 应用内自治关键场景通过
- 专家能力调度已按元数据与知识域收敛
- Ollama 默认 Qwen3.5 候选显示正确

## 当前边界

- 固定管家层首次预热可能持续较长时间，但不应阻塞 GUI
- 多节点真实实机联调仍需继续推进，当前正式复验仍以虚拟 Pi 与文件驱动链路为主
- 第三方语音扩展板兼容性问题不纳入当前版本正式通过项

## 当前正式交付文件

- `D:\NeuroLab\release\NeuroLab-Hub-Setup-v1.0.0.exe`
- `D:\NeuroLab\release\NeuroLab_Hub_1.0.0.zip`
- `D:\NeuroLab\release\NeuroLab_Hub_1.0.0_fresh_validation.zip`
