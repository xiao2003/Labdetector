# NeuroLab Hub 1.0.1 测试报告

版本：1.0.1  
报告日期：2026-03-23

## 1. 目标

本报告用于确认 `1.0.1` 是否满足“从发布 `zip` 到实验室成功部署”的发布前放行标准。

## 2. 测试范围

本轮覆盖：

- 新机首启
- GUI 全模块核心链路
- 模型选择
- 公共知识导入
- 专家资产导入与专家知识导入
- `LLM` 训练与视觉训练最小闭环
- 单节点 `PC-Pi` 闭环
- `4` 节点 `PC-Pi` 并发闭环
- 音频文件驱动的 `Pi` 本地识别上行
- 视觉事件 -> 专家分析 -> 结果回传 -> ACK

## 3. 测试环境

- Windows：当前工作站
- Python：3.11
- 打包形态：`SilentDir/onedir`
- `Pi` 形态：虚拟 `Pi` 测试节点
- 音频格式：`wav / 16kHz / mono / PCM16`

## 4. 执行结果

### 4.1 Pi 音频回放链路

执行：

```powershell
python -m unittest pi.testing.test_audio_replay
```

结果：通过。

说明：音频文件已进入 `Pi` 端真实离线识别链路，并成功产出唤醒和文本命令。

### 4.2 音频 + 视觉闭环基础验证

执行：

```powershell
python -m pc.testing.virtual_text_voice_closed_loop_test
```

结果：通过。

报告：

- `release/virtual_text_voice_closed_loop_report.json`

说明：已确认语音文本回传、视觉专家结果回传与 `ACK` 全部成立。

### 4.3 单节点 GUI 发布验收

执行：

```powershell
python -m pc.testing.gui_release_acceptance_test --node-count 1 --report-file release/gui_release_acceptance_single.json
```

结果：通过。

报告：

- `release/gui_release_acceptance_single.json`

### 4.4 四节点 GUI 发布验收

执行：

```powershell
python -m pc.testing.gui_release_acceptance_test --node-count 4 --report-file release/gui_release_acceptance_multi4.json
```

结果：通过。

报告：

- `release/gui_release_acceptance_multi4.json`

## 5. 本轮确认通过的能力

### 5.1 GUI 功能

- 主界面启动
- 系统自检
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

### 5.2 PC-Pi 闭环

- 单节点节点发现
- `4` 节点节点发现
- 语音识别文本上行
- 知识问答/语音调用类模型路由
- 视觉专家事件上行
- 结构化专家结果回传
- `Pi` 端播报文本接收
- `ACK` 成功

## 6. 本轮修复的关键问题

- 启动页停留过长
- 双重启动页
- 训练工作台启动空指针
- 本地代理劫持虚拟 `Pi` WebSocket
- 系统事件流在不同分辨率下漂移
- 离线节点数统计语义错误
- 顶部目录栏在不同分辨率下挤压
- `Pi` 远端文本命令误触发 `PC` 本地完整语音栈
- `Pi` 唤醒词同步未真实生效
- GUI 后台线程直接读取 Tk 状态导致主线程错误

## 7. 当前边界

- 真实树莓派硬件尚未接入现场联调
- 多节点通过的是虚拟 `Pi`，不是实机集群
- 当前工作区不是 `git` 仓库，无法执行真实远端推送

## 8. 结论

结论：当前代码基线已满足 `1.0.1` 发布候选标准，可继续执行小体量 `SilentDir` 发布包重打、独立目录回归和白名单清扫。
