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

- 安装包交付层
- 新机首启
- 真实安装包首启 smoke
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
- 应用内自治关键动作
- 专家能力驱动调度

## 三、固定管家层运行时说明

### 3.1 资产组成

发布链固定包含：

- `llama.cpp` Windows CPU runtime
- 固定管家层运行时封装代码
- 固定模型下载清单 `pc/models/orchestrator/orchestrator_assets.json`

安装包不直接包含 GGUF 文件。GGUF 会在首次启动 GUI 显示后后台下载到可写运行时目录。

当前固定资产已经锁定为：

- runtime：`llama.cpp` Windows CPU 运行时
- 模型：`Qwen2.5-1.5B-Instruct` 官方 GGUF 量化文件

固定管家层模型采用“版本锁定 + 校验锁定”，下载完成后必须通过校验后才进入预热阶段。

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
- `warming_up`
- `download_failed`
- `ready`

当固定管家层还未 `ready` 时，系统使用确定性规则链，`planner_backend=deterministic`。固定管家层就绪后，再切换到 `planner_backend=embedded_model`。

当前正式口径补充为：

- 模型文件缺失时，首启进入后台下载，不阻塞 GUI
- 首次预热耗时较长时，状态保持 `warming_up`
- 只有真正校验失败或运行时异常时，才进入 `download_failed`

## 四、测试方法

### 4.0 正式验收范围

当前正式验收不是局部函数验证，而是从安装包开始，到 `PC-Pi` 语音/视频闭环结束，覆盖 6 层架构、每层功能与层间协作。

正式验收层次固定为：

1. 安装包交付层
2. 首次启动与运行时层
3. 交互与展示层
4. 管家编排层
5. 执行与知识层
6. 通信与节点管理层
7. Pi 轻前端边缘层
8. `PC-Pi` 语音闭环
9. `PC-Pi` 视频闭环
10. 应用内自治

### 4.1 分层验收矩阵

#### 安装包交付层

- `Setup.exe` 安装成功
- 安装后主程序入口存在
- 安装目录结构正确
- 固定管家层 runtime 随安装包存在
- 模型资产清单存在

#### 首次启动与运行时层

- GUI 首次启动不长时间等待
- 固定管家层后台准备链被触发
- 运行时状态正确写入：
  - `not_installed`
  - `downloading`
  - `warming_up`
  - `ready`
  - `download_failed`
- 未就绪前 `planner_backend=deterministic`
- 就绪后 `planner_backend=embedded_model`

#### 交互与展示层

- 页面切换正常
- 事件流展示可用
- 事件流筛选可用（全部 / 告警 / 调度 / 系统）
- 首屏状态收敛为：
  - `系统已可用`
  - `后台准备中`
  - `后台准备失败（已回退规则链）`
- 最新高优事件卡片可在高危事件后更新
- 管家自治动作会以可视化摘要进入事件流
- 自治动作摘要必须包含“动作 -> 结果”
- 模型选择可用
- Ollama 候选显示正确
- 用户主动触发的知识问答、系统状态查询、专家调用入口可用
- 知识导入状态必须显示业务结果：
  - `最近一次导入`
  - `作用域`
  - `新增文档`
  - `时间戳`

#### 管家编排层

- 语音文本统一进入 `orchestrator.plan_voice_command()`
- 边缘事件统一进入 `orchestrator.plan_edge_event()`
- 不存在基于固定场景名的硬编码专家主链
- 管家层未就绪时规则链可用
- 管家层就绪后嵌入模型链可用

#### 执行与知识层

- 全局知识问答可用
- 专家知识域增强可用
- 执行层模型切换后路由不变、内容可变
- `lab_qa_expert` 可正常参与全局链路

#### 通信与节点管理层

- PC 与 Pi 的发现、连接、状态同步可用
- 远端消息统一进入 orchestrator
- 回传文本、播报、日志摘要按 `pi_id` 隔离
- ACK 正常

#### Pi 轻前端边缘层

- 唤醒词与唤醒别名可用
- 轻量 ASR 输出正确
- 本地 TTS 正常
- `停止播报` 可本地打断
- 低频视觉前置检测可上行事件
- `pi_cli status` 正确反映轻前端角色

### 4.2 代码与最小回归

推荐至少执行：

```powershell
python -m unittest   pc.testing.test_orchestrator_runtime   pc.testing.test_orchestrator_model   pc.testing.test_expert_manager_voice_routing   pc.testing.test_monitoring_speech_policy   pc.testing.test_remote_voice_routing   pi.testing.test_voice_interaction   pi.testing.test_runtime_installer   pi.testing.test_pi_config
```

### 4.3 Pi 语音闭环

无真实语音板时，使用音频文件驱动验证：

- `pi/testing/audio_replay.py`
- `pi/testing/closed_loop_bridge.py`

验证目标：

- 音频文件进入 Pi 本地识别链
- 唤醒与命令识别正确上行
- PC 统一进入 orchestrator
- 执行层模型或专家执行链正常回传
- Pi 本地播报与停止播报正常

### 4.4 视频闭环

验证目标：

- Pi 边缘事件统一进入 `orchestrator.plan_edge_event()`
- 普通提醒只写事件摘要流，不自动播报
- 强告警自动播报
- 用户主动请求时触发关键帧上传和专家分析

### 4.5 首启体验验证

正式验证要求：

1. 用安装包在干净环境安装
2. 第一次启动程序
3. 确认主界面先出现
4. 确认固定管家层模型下载/预热只在后台开始
5. 确认 GUI 可操作
6. 确认后台状态可观测

推荐使用：

- `pc/testing/installer_first_launch_smoke.py`

验证项至少包括：

- 安装器退出码
- 安装后主程序存在
- 外层启动器是否拉起后台 `pythonw`
- 固定管家层状态时间线
- 观察窗口结束时的最终状态

补充说明：

- 当前安装包采用 `PrivilegesRequired=admin`
- 若在**非管理员会话**中执行首启 smoke，脚本现在会明确写出：
  - `install_blocked = true`
  - `install_blocked_reason = installer_requires_admin`
- 这种结果表示**当前会话权限不足，无法完成静默安装验证**，不应误判为安装包本体损坏

当前真实首启 smoke 已验证通过，报告文件为：

- `release/smoke_install_formal_acceptance_20260329.json`

本轮又补了一次管理员态真实安装验证，报告文件为：

- `release/smoke_install_formal_acceptance_admin_20260329_r8.json`

管理员态报告已确认：

- 安装器退出码为 `0`
- 安装目录内主程序存在
- 首启成功拉起后台 `pythonw`
- 固定管家层运行时目录与状态文件已在本地写出
- 当前环境下固定模型下载触发了 `download_failed`
- `planner_backend` 仍保持为 `deterministic`

补充说明：

- 这轮管理员态真实验证已采到完整错误路径
- 根因是固定模型后台下载触发 SSL EOF
- 这说明安装链与 GUI 首启链是通的，但当前环境下外网模型下载不稳定
- 系统已按正式设计回退到规则链，不阻塞 GUI，也不导致主程序不可用

### 4.6 专家能力驱动调度验证

当前正式要求是：专家调度依据专家元数据、知识域可用性、输入类型与上下文，不依赖固定场景硬编码。

本轮至少验证：

- `expert_registry` 中的能力元数据可被统一读取
- 专家知识域缺失时，系统会降为“无知识增强执行”，而不是误判专家不存在
- 新增专家能力事实后，无需修改核心路由即可进入候选

### 4.7 Ollama 默认模型清单验证

当前 GUI 中 Ollama 内置候选必须显示：

- `qwen3.5:4b`
- `qwen3.5:9b`
- `qwen3.5:27b`
- `qwen3.5:35b`

验证要求：

- 本地无模型时回退到该默认列表
- 本地有 `ollama list` 结果时优先显示本机已安装模型
- 自定义模型入口仍可用

### 4.8 事件流筛选与自治痕迹验证

当前正式 GUI 口径要求：

- 事件流支持 `全部 / 告警 / 调度 / 系统` 四类筛选
- 首屏状态只暴露三态产品文案
- 事件流顶部存在“最新高优事件”常驻摘要卡片
- 管家自动执行应用内动作时，事件流中会出现自治动作摘要

至少验证：

- 普通监控日志可在 `全部` 中看到
- 高优告警可在 `告警` 中被单独筛出
- 触发高危事件后，高优事件卡片必须同步更新
- 管家自动动作可在 `调度` 中看到，例如：
  - `管家已执行动作: start_monitoring -> 监控已启动`
  - `管家已执行动作: open_view -> 已切换到知识中心`
  - `管家已执行动作: query_system_status -> 系统自检已发起`
- `系统` 视图中保留启动、自检、连接等系统级日志
- 知识导入完成后，底部状态栏要直接展示业务结果，而不是仅显示导入成功/失败计数

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
- 真实安装包首启 smoke 已验证“GUI 先显示 + 模型后台准备”
- GUI Ollama 模型选择已验证包含 `qwen3.5:4b / 9b / 27b / 35b`
- 专家调度已验证以专家元数据与知识域可用性为事实来源

本轮关键修复点已经纳入正式验证口径：

- `pc/voice/voice_interaction.py` 的重复语音分发定义已收敛
- `pc/core/monitoring_policy.py` 已成为监控播报策略唯一来源
- GUI 闭环测试已隔离固定管家层状态目录，避免污染真实用户目录
- `desktop_app.py` 已在窗口关闭阶段增加流刷新与状态刷新保护，避免测试退出后残留 Tk 回调异常
- GUI 首屏状态已经收敛为三态产品文案
- 最新高优事件卡片与自治动作结果摘要已纳入正式 GUI 验收
- 知识导入反馈已改为作用域 / 新增文档 / 最近一次导入时间的业务结果展示

当前本轮实际已重跑并通过的正式验收主链包括：

1. 固定管家层运行时与编排单测
2. 专家语音路由与能力事实单测
3. 监控播报策略单测
4. 远端 Pi 语音路由单测
5. Pi 轻前端配置与语音线程单测
6. Ollama 默认模型清单与 GUI 推荐列表单测
7. 音频文件驱动语音闭环
8. GUI 完整闭环
9. GUI 发布验收
10. 安装包首启 smoke

本轮关键报告文件为：

- `release/smoke_install_formal_acceptance_20260329.json`
- `release/formal_acceptance_virtual_closed_loop_20260329.json`
- `release/gui_full_closed_loop_20260329.json`
- `release/gui_release_acceptance_20260329.json`

当前正式通过标准已经满足：

- 安装包交付通过
- 首次启动 smoke 通过
- 6 层关键功能与层间协作通过
- `PC-Pi` 语音闭环通过
- `PC-Pi` 视频闭环通过
- 应用内自治关键场景通过
- Ollama 模型清单修正通过
- 文档与 Release 应保持一致

## 七、文档入口

- 项目总览与使用手册：[`docs/NeuroLab_Hub_项目总览与使用手册.md`](./NeuroLab_Hub_项目总览与使用手册.md)
- 版权与软著材料：[`docs/NeuroLab_Hub_版权与软著材料.md`](./NeuroLab_Hub_版权与软著材料.md)
- 文档归档索引：[`docs/archive/README.md`](./archive/README.md)
