# NeuroLab Hub 1.0.0 正式发布说明

版本：1.0.0  
发布日期：2026 年 3 月  
发布形态：Windows 轻量启动包 + Raspberry Pi `pi/` 目录协同部署

## 一、发布目标

本版本用于形成 NeuroLab Hub 第一版正式软件基线，作为：

1. 软件交付与演示基线
2. 软件著作权登记版本基线
3. 后续 Raspberry Pi 实机联调的统一代码与文档口径

本版本的目标不是覆盖全部硬件边界，而是在已验证的软件主链基础上，提供一套可安装、可启动、可联调、可说明、可申报的正式版本。

## 二、正式发布物

### 2.1 GitHub Release 附件

当前正式发布附件为：

1. `NeuroLab_Hub_1.0.0.zip`
2. `NeuroLab_Hub_1.0.0_fresh_validation.zip`

说明：
- 第一项为主交付包。
- 第二项为带“新机复验”结果口径的复验包。

### 2.2 本地构建产物归档

本地已整理 `1.0.0` 命名副本，位于：

- `release/local_build_1.0.0/`

其中包含：

1. `NeuroLab_Hub_1.0.0_SilentDir.exe`
2. `NeuroLab_Hub_1.0.0_Windows.exe`
3. `NeuroLab_Hub_1.0.0_LLM.exe`
4. `NeuroLab_Hub_1.0.0_Vision.exe`

## 三、正式交付口径

### 3.1 Windows 端

当前正式推荐交付形态为：

- `NeuroLab Hub SilentDir.exe`
- `_internal/`
- `APP/`

不再以 `onefile` 作为正式目标。

### 3.2 Raspberry Pi 端

当前正式推荐交付形态为：

- `pi/` 目录整体复制
- 通过 `pc/一键配置树莓派.cmd` 完成首轮接入、Wi‑Fi 配置、代码投递与后台自治安装
- `Pi` 安装完成后执行 `bash start_pi_node.sh`

## 四、本版本已验证范围

本版本已完成下列范围的验证：

1. Windows 主程序启动烟测
2. LLM 训练入口启动烟测
3. 视觉训练入口启动烟测
4. GUI 核心模块入口与主操作链验证
5. 模型选择、知识导入、专家模型编排、专家知识导入验证
6. LLM 训练工作区与视觉训练工作区最小闭环验证
7. 单节点与四节点虚拟 Pi 闭环验证
8. 音频文件驱动的 Pi 语音识别上行验证
9. 新机路径解压、首启和换机复验验证
10. Pi 自治安装与状态查询链验证

## 五、当前明确边界

本版本仍存在以下边界，不应超出此范围对外表述：

1. 当前多节点闭环通过的是虚拟 Pi 节点，不是实物集群长期联调。
2. 当前真实 Raspberry Pi 的摄像头、麦克风、扬声器链路仍需继续实机联调。
3. 某些第三方语音扩展板存在硬件兼容性与上电异常风险，当前不纳入本版本正式通过项。
4. 真实音频阵列硬件能力不作为 `1.0.0` 正式发布的前置门槛。

## 六、推荐演示口径

对外演示时，建议统一表述为：

- NeuroLab Hub 1.0.0 已完成中心端、边缘端、专家分析、知识导入、训练入口和闭环联调主链验证。
- Raspberry Pi 实机视觉链与边缘接入链具备继续联调基础。
- 语音闭环在当前版本支持通过音频文件驱动和虚拟 Pi 路径验证。
- 某些特定第三方音频扩展硬件仍在独立排障，不影响软件系统主版本基线成立。

## 七、配套文档

建议与本发布说明一并使用的文档：

1. `docs/product/NeuroLab_Hub_软件说明书.md`
2. `docs/product/NeuroLab_Hub_用户手册.md`
3. `docs/product/NeuroLab_Hub_完整手册.md`
4. `docs/product/NeuroLab_Hub_真实树莓派接入联调清单.md`
5. `docs/release/NeuroLab_Hub_PC_PI_测试过程手册.md`
6. `docs/release/NeuroLab_Hub_测试报告_1.0.0.md`
7. `docs/compliance/NeuroLab_Hub_软著提交口径摘要_1.0.0.md`

## 八、结论

NeuroLab Hub `1.0.0` 已形成正式版本基线，可作为：

1. 发布归档版本
2. 软著提交版本
3. 后续 Pi 实机联调版本
4. 对外演示与阶段性验收版本
