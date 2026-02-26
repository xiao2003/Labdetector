# 🛠️ 树莓派 5 远程开发：PyCharm 环境配置实战文档

## 1. 核心目标
建立一个**“本地编辑 -> 自动同步 -> 远程执行”**的闭环，彻底解决在不同网络环境（如手机热点、实验室 WiFi）切换开发时，IDE 路径映射混乱导致的 `/tmp/pycharm_project_xxx` 找不到文件报错问题。

---

## 2. 环境清单
* **硬件**：树莓派 5 (Alexander)
* **网络**：局域网 / 手机热点 (使用 `nmcli` 命令行注入连接)
* **IDE**：PyCharm Professional (Paid Tier)
* **解释器**：远程 Python 3.13 (位于虚拟环境 `yolo_env`)

---

## 3. 配置全流程 (避坑精华版)

### 第一步：建立 SSH 与同步映射 (Deployment)
1.  **菜单路径**：`Settings` -> `Build, Execution, Deployment` -> `Deployment`。
2.  **Connection 标签**：设置 `Root Path` 为 `/home/alexander`。
3.  **Mappings 标签**：
    * **Local Path**: `D:\Labdetector\piside`
    * **Deployment Path**: `Labdetector/piside` (注意：此相对路径会与 Root Path 自动拼接)。
4.  **关键点**：配置完成后，必须手动右键左侧项目文件夹执行 `Deployment` -> `Upload`，确保树莓派物理路径中存在该目录。

### 第二步：配置项目解释器 (Interpreter)
1.  **添加方式**：点击 PyCharm 右下角状态栏 -> `Add New Interpreter` -> `On SSH`。
2.  **路径指向**：手动填入虚拟环境 Python 路径 `/home/alexander/yolo_env/bin/python`。
3.  **底层基因修正 (彻底根除 /tmp 报错)**：
    * 若运行报错找不到文件，进入 `Show All...` 解释器列表。
    * 点击 **Path Mappings** 图标（文件夹映射图标）。
    * **删除**所有包含 `/tmp/pycharm_project_xxx` 的默认记录。
    * **手动添加**：`D:\Labdetector\piside` <==> `/home/alexander/Labdetector/piside`。

### 第三步：同步 Python 控制台 (Console)
1.  **菜单路径**：`Settings` -> `Python Console`。
2.  **纠偏**：修改其中的 `Working directory` 和 `Path mappings`，确保其与第二步的解释器映射路径完全一致。
3.  **生效**：点击控制台左侧红色方块 **⏹️** 彻底杀死旧进程并重启控制台。

---

## 4. 常见报错及排查逻辑

| 报错现象 | 根源分析 | 解决方法 |
| :--- | :--- | :--- |
| `cd: /tmp/xxx: No such file` | 解释器底层路径映射未更新或存在旧缓存 | 物理删除该解释器配置，在确保 Deployment 路径正确后重新添加 |
| `ModuleNotFoundError: pcside` | PyCharm 跨设备自动导包错误 | 删掉跨设备导入（如 `from pcside import...`），改为本地标准 `import` |
| `ModuleNotFoundError: vosk` | 远程虚拟环境缺少第三方依赖库 | 在终端执行 `/home/alexander/yolo_env/bin/pip install vosk` |

---
> **Tip**: 建议将手机热点设置为树莓派的备用 WiFi 优先级。当环境网络不可用时，开启热点即可通过 `pi5.local` 或固定 IP 快速重连。