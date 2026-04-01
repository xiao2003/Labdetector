# NeuroLab Hub fresh validation 1.0.0

- 生成时间：2026-04-01 11:40:52
- 复验结论：通过
- 复验范围：GUI 发布验收、PC-Pi 语音闭环、交付物复核

## 核心结果

- GUI 发布验收：通过
- PC-Pi 语音闭环：通过
- 固定管家层状态：ready
- planner_backend：embedded_model
- Full 安装包：内置 Vosk 与固定管家层 llama.cpp + Qwen3.5-0.8B Q4_K_M
- 开发包：包含 exe、源码与内置语音/管家资产，不包含外部执行层模型
- 极简包：用于自检/自愈验证，不包含 `_internal`、Vosk、固定管家层组件与 GGUF

## 交付物

- Setup.exe：`D:\NeuroLab\release\NeuroLab-Hub-Setup-v1.0.0.exe`
- 开发包：`D:\NeuroLab\release\NeuroLab_Hub_1.0.0.zip`
- 极简包：`D:\NeuroLab\release\NeuroLab_Hub_1.0.0_minimal.zip`

## 关键报告

- GUI 发布验收：`D:\NeuroLab\release\gui_release_acceptance_demo.json`
- 语音闭环：`D:\NeuroLab\release\voice_closed_loop_demo_post_scheduler.json`

## 演示建议口令

- 介绍当前系统状态
- 分析当前实验风险并给出处置建议

## 说明

- 本轮复验重点确认 PC 端管家语音处理、专家知识链、固定管家层就绪状态和交付物边界。
- 外部执行层模型继续由用户自行安装或下载，不内置于正式交付物。
