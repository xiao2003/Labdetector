# NeuroLab Hub PC-Pi 测试过程手册

版本：1.0.0

## 1. 目的

本手册用于说明 `1.0.0` 发布前的正式验收流程。验收口径已经统一为“普通用户从下载 `zip` 到在实验室成功部署”的完整旅程，而不是单纯源码冒烟。

## 2. 验收范围

当前正式验收覆盖：

- 新机首启与轻量 `exe` 交付
- GUI 全模块实测
- 模型选择、知识导入、专家模型编排、专家知识导入
- `LLM` 训练与视觉训练
- `PC-Pi` 单节点闭环
- `PC-Pi` `4` 节点闭环
- 音频文件驱动的 `Pi` 本地识别上行
- 视觉事件上送、专家分析、结果回传与 ACK

## 3. 测试前提

### 3.1 Windows 端

- Windows 10/11
- Python 3.11
- 可用 GPU 优先
- 已安装或允许自检安装 Ollama

### 3.2 Pi 端

正式验收阶段先使用虚拟 `Pi`，真实硬件接入作为后续阶段。

### 3.3 音频格式

所有语音样本统一采用：

- `wav`
- `16kHz`
- `mono`
- `PCM16`

## 4. 当前正式测试入口

### 4.1 Pi 音频回放链路测试

```powershell
python -m unittest pi.testing.test_audio_replay
```

预期：

- `Pi` 侧真实离线识别链路可以从音频文件得到唤醒与命令文本

### 4.2 音频 + 视觉闭环基础验证

```powershell
python -m pc.testing.virtual_text_voice_closed_loop_test
```

预期：

- 至少 1 条音频驱动语音闭环通过
- 至少 1 条视觉闭环通过
- `CMD:TTS`、`CMD:EXPERT_RESULT` 与 `ACK` 成功

### 4.3 单节点 GUI 发布验收

```powershell
python -m pc.testing.gui_release_acceptance_test --node-count 1 --report-file release/gui_release_acceptance_single.json
```

预期：

- GUI 主界面与核心窗口可打开
- 模型选择、知识导入、专家导入、训练、标注、档案、模型配置通过
- 单节点语音 + 视觉闭环通过

### 4.4 四节点 GUI 发布验收

```powershell
python -m pc.testing.gui_release_acceptance_test --node-count 4 --report-file release/gui_release_acceptance_multi4.json
```

预期：

- `4` 个虚拟 `Pi` 全部上线
- 每个节点至少完成 1 条语音闭环和 1 条视觉闭环
- 节点数统计、状态栏、事件流和结果归属一致

## 5. 正式执行顺序

1. 清理运行时缓存，模拟新机
2. 运行 `pi.testing.test_audio_replay`
3. 运行 `pc.testing.virtual_text_voice_closed_loop_test`
4. 运行单节点 GUI 发布验收
5. 运行 `4` 节点 GUI 发布验收
6. 汇总测试报告
7. 重打 `SilentDir` 发布包
8. 从发布 `zip` 独立目录解压并再次回归
9. 白名单清扫目录

## 6. 本轮重点验证点

### 6.1 GUI 真实操作链

当前 GUI 验收固定包含：

- 主程序首启
- 模型选择
- 公共知识导入
- 专家资产导入
- 专家知识导入
- 专家编排
- `LLM` 训练工作区与数据导入
- 视觉训练工作区与数据导入
- 标注窗口最小交互
- 档案刷新
- 模型配置窗口打开
- 开始监控

### 6.2 语音闭环

当前语音链路要求：

- 禁止纯文本伪造命令替代 `Pi` 端识别
- 必须从音频文件进入 `PiVoiceRecognizer`
- 验收以关键词匹配为准，不要求逐字完全相等

### 6.3 视觉闭环

当前视觉链路要求：

- 触发专家策略
- 上送视觉事件
- `PC` 输出结构化专家结果
- `Pi` 完成 ACK

## 7. 当前报告文件

- `release/virtual_text_voice_closed_loop_report.json`
- `release/gui_release_acceptance_single.json`
- `release/gui_release_acceptance_multi4.json`

## 8. 放行标准

只有以下条件全部满足，才允许进入发布收口：

- 新机首启通过
- 单节点 GUI 验收通过
- `4` 节点 GUI 验收通过
- 音频文件驱动语音闭环通过
- 视觉闭环通过
- 文档基线更新完成
- `SilentDir` 小体量发布包重打通过

## 9. 当前阻塞说明

当前工作区不是 `git` 仓库，因此正式“推送远端”不属于当前可执行动作。发布阶段只能停在“已验证的发布产物与文档”这一层。
