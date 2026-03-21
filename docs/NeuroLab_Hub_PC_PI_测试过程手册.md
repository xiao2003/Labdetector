# NeuroLab Hub PC-Pi 测试过程手册

## 1. 目的

本手册用于指导交付前验收，覆盖以下范围：

- PC 单机功能测试
- GUI 静默回归
- 语音状态机测试
- 视觉训练与标注测试
- PC-Pi 单节点闭环测试
- PC-Pi 多节点压力闭环测试

测试目标是确认：

- 生产功能不依赖 `tmp/` 中的临时测试脚本
- `pc/` 与 `pi/` 可独立交付
- 所有测试逻辑统一归档到 `test/pc` 与 `test/pi`

## 2. 环境要求

- Windows 10 / 11
- Python 3.11
- 可用 GPU 优先，但 CPU 也应能完成基础验证
- 已安装 Ollama，并至少存在一个本地可用模型
- 麦克风、扬声器、摄像头可用

## 3. 测试分层

### 3.1 PC 单机功能
- GUI 启动
- 系统自检
- 单机监控
- 语音唤醒与控制词
- 标注与训练面板
- 知识库导入

### 3.2 Pi 闭环功能
- 单节点闭环
- 多节点闭环
- 视觉事件上送
- 语音命令上送
- PC 结果回传与 Pi 播报

### 3.3 压力与稳定性
- 多节点并发
- 弱预览帧 + 关键帧裁剪
- 训练任务冒烟
- GUI 静默点击回归

## 4. 推荐执行顺序

1. `python test/pc/auto_module_test.py`
2. `python test/pc/run_gui_silent_test.py`
3. `python test/pc/test_visual_training_pipeline.py`
4. `python test/pi/test_pc_pi_integrated_bridge.py`
5. `python test/pi/test_pc_pi_llm_interpreter_closed_loop.py`

## 5. 具体测试项

### 5.1 模块总回归

命令：

```powershell
python test/pc/auto_module_test.py
```

预期：
- `pass_count > 0`
- `fail_count = 0`

### 5.2 GUI 静默回归

命令：

```powershell
python test/pc/run_gui_silent_test.py
```

预期：
- 所有步骤均为 `pass`

### 5.3 视觉训练冒烟

命令：

```powershell
python test/pc/test_visual_training_pipeline.py
```

预期：
- `ok = true`
- `best_weights` 文件存在

### 5.4 聚焦知识图像测试

命令：

```powershell
python test/pc/test_focused_knowledge_image.py
```

预期：
- PPE 知识域与危化品知识域都能命中新导入知识
- 合成图像仍能触发对应专家结果

### 5.5 PC-Pi 单节点 / 多节点闭环

命令：

```powershell
python test/pi/test_pc_pi_integrated_bridge.py
```

预期：
- `single_node_pass = pass`
- `multi_node_stress = pass`

### 5.6 知识库 + 统一解释层闭环

命令：

```powershell
python test/pi/test_pc_pi_llm_interpreter_closed_loop.py
```

预期：
- 所有子项 `pass`

## 6. 人工验收要点

- 启动页排版正常
- 单机模式下不显示节点日志区
- WebSocket 模式下主系统事件流与节点日志区分离
- 语音控制词优先级正确
- Pi 侧可收到 PC 回传播报

## 7. 交付前清单

- [ ] 测试脚本已归档到 `test/pc`、`test/pi`
- [ ] `tmp/` 不再存放测试入口脚本
- [ ] GUI 静默测试通过
- [ ] 模块总回归通过
- [ ] 视觉训练冒烟通过
- [ ] PC-Pi 单节点与压力闭环通过
- [ ] 生成轻量 EXE
- [ ] 生成安装包
- [ ] 清扫本地临时残留
- [ ] 确认 `.gitignore` 生效
