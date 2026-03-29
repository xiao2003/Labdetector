# NeuroLab Hub 1.0.0 新安装链路复验总结

## 目标

基于当前正式安装链路，完成一轮围绕 `1.0.0` 的真实复验，覆盖：

- 正式安装包安装
- 首次启动 GUI 体验
- 固定管家层后台下载与后台预热
- `PC-Pi` 语音与视频闭环主链
- GUI 关键功能与多节点场景

## 当前正式架构

当前版本按 6 层主链收敛：

1. 交互与展示层
2. 会话与运行时层
3. 管家编排层
4. 执行与知识层
5. 通信与节点管理层
6. Pi 轻前端边缘层

其中固定管家层模型采用：

- `Qwen2.5-1.5B-Instruct`
- 项目内置 `llama.cpp` Windows CPU runtime
- 首次启动后后台下载固定 GGUF
- 后台预热完成前，系统保持 `planner_backend=deterministic`

当前固定下载清单已锁定为：

- runtime：`llama.cpp` Windows CPU 运行时
- 模型：`Qwen2.5-1.5B-Instruct` 官方 GGUF 量化文件

## 本轮关键验证点

### 1. 真实安装包首启 smoke

安装包：

- `D:\NeuroLab\release\NeuroLab-Hub-Setup-v1.0.0.exe`

验证脚本：

- `D:\NeuroLab\NeuroLab Hub\pc\testing\installer_first_launch_smoke.py`

当前结论：

- 安装器安装成功
- 安装后 `NeuroLab Hub.exe` 存在
- 首次启动时，外层启动器会很快退出
- 后台 `pythonw` 进程会继续存活
- 这说明 GUI/后台主程序已被成功拉起
- 固定管家层模型准备链在 GUI 出现后于后台执行
- 当前 smoke 报告：`D:\NeuroLab\release\smoke_install_20260329_124300.json`

### 2. 固定管家层状态机

本轮已确认：

- 模型文件缺失时，状态进入 `downloading`
- 下载完成后进入 `warming_up`
- 首次预热耗时较长时，状态保持 `warming_up`
- 不再把预热超时误写成 `download_failed`
- 真正异常时才进入 `download_failed`

### 3. 语音闭环

本轮正式口径不是“文本伪造”，而是：

- 使用音频文件驱动 Pi 本地识别链
- 识别出的文本进入 `PC` 端统一 `orchestrator`
- 再由执行层模型/专家执行链生成结果
- 结果回传并完成播报

### 4. 视频闭环

本轮正式口径为：

- Pi 低频前置检测
- 边缘事件统一进入 `orchestrator.plan_edge_event()`
- 专家分析、知识补充、播报策略在 PC 端统一编排
- 强告警自动播报
- 普通提醒仅写事件摘要流

## 本轮执行的验证

### 单元与结构回归

已通过：

- `pc.testing.test_orchestrator_runtime`
- `pc.testing.test_orchestrator_model`
- `pc.testing.test_expert_manager_voice_routing`
- `pc.testing.test_monitoring_speech_policy`
- `pc.testing.test_remote_voice_routing`
- `pc.testing.test_gui_knowledge_dispatch`
- `pc.testing.test_protocol_ws_port`
- `pc.testing.test_pi_one_click_setup`
- `pi.testing.test_voice_interaction`
- `pi.testing.test_runtime_installer`
- `pi.testing.test_pi_config`
- `pi.testing.test_audio_replay`
- `pi.testing.test_voice_model_path`
- `pi.testing.test_model_downloader_offline`

### 集成与闭环验证

已通过：

- `pc.testing.virtual_text_voice_closed_loop_test`
- `pc.testing.gui_full_closed_loop_test`
- `pc.testing.gui_release_acceptance_test`

当前关键结果：

- 单元与结构回归：`27` 项通过，`1` 项跳过
- 关键集成闭环：`3` 项通过
- 旧的 Ollama 直连依赖已从这 3 条验证主链中移除
- GUI 关闭阶段的残留 Tk 回调异常已收口

### 首启 smoke

已通过：

- 安装包安装成功
- 首启后后台主进程成功拉起
- 固定管家层后台准备链被触发

## 当前正式结论

基于当前新安装链路，`NeuroLab Hub 1.0.0` 已完成一轮围绕正式安装包和统一编排主链的复验：

- 安装包可安装
- 首次启动不会先卡死在固定模型加载上
- GUI 主链先显示
- 固定管家层模型在后台下载和后台预热
- `PC-Pi` 语音/视频闭环已统一进入单一编排主链
- Pi 侧仍保持轻前端角色

## 当前边界

- 固定管家层首次后台预热可能持续较长时间，但不应阻塞 GUI
- 多节点真实实机联调仍需继续推进，目前正式验证仍以虚拟 Pi 与文件驱动链路为主
- 第三方语音扩展板兼容性问题不纳入当前版本正式通过项

## 当前正式交付文件

- `D:\NeuroLab\release\NeuroLab-Hub-Setup-v1.0.0.exe`
- `D:\NeuroLab\release\NeuroLab_Hub_1.0.0.zip`
- `D:\NeuroLab\release\NeuroLab_Hub_1.0.0_fresh_validation.zip`
- `D:\NeuroLab\release\NeuroLab_Hub_1.0.0_fresh_validation_20260329_r5.zip`
