# 固定管家层运行时目录

该目录用于随项目分发固定管家层模型的本地推理运行时。

当前默认约定：

- 运行时文件名：`llama-cli.exe`
- 调用方式：由 [`D:\NeuroLab\NeuroLab Hub\pc\core\orchestrator_runtime.py`](D:/NeuroLab/NeuroLab%20Hub/pc/core/orchestrator_runtime.py) 统一封装

本轮只完成运行时封装与接入路径，不在仓库中直接提交二进制。
