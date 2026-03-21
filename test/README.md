# 测试目录说明

本目录用于存放 **不随交付版本直接进入生产运行目录** 的测试脚本与测试说明。

## 目录划分

### `test/pc`
- PC 单机功能测试
- GUI 静默回归
- 视觉训练与标注流程测试
- 语音状态机与语音知识提取测试
- 人工测试辅助脚本

### `test/pi`
- 虚拟 Pi 节点模拟
- PC-Pi 闭环测试
- 单节点 / 多节点 / 压力测试
- 知识库 + 统一解释层闭环测试

## 设计原则

- 生产逻辑保留在 `pc/` 和 `pi/`
- 测试逻辑保留在 `test/`
- 临时报告、日志和构建中间产物默认写入 `tmp/`
- 上传 GitHub 时，保留源码和测试脚本，不提交临时运行产物

## 常用测试入口

### GUI 静默回归

```powershell
python test/pc/run_gui_silent_test.py
```

### 模块总回归

```powershell
python test/pc/auto_module_test.py
```

### 视觉训练冒烟

```powershell
python test/pc/test_visual_training_pipeline.py
```

### 聚焦知识图像测试

```powershell
python test/pc/test_focused_knowledge_image.py
```

### 语音运行环境快速检查

```powershell
python test/pc/check_runtime_env.py
```

### 危化品语音路由探针

```powershell
python test/pc/probe_voice_expert.py
```

### PC-Pi 一体化闭环测试

```powershell
python test/pi/test_pc_pi_integrated_bridge.py
```

### 知识库 + 统一解释层闭环测试

```powershell
python test/pi/test_pc_pi_llm_interpreter_closed_loop.py
```
