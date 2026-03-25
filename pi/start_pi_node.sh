#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 统一在脚本目录内启动，避免从桌面、文件管理器或其他目录点击启动时路径漂移。
cd "$SCRIPT_DIR"
export PYTHONUTF8=1

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"

# 固定使用项目根目录虚拟环境，避免依赖污染系统 Python。
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "[INFO] 未检测到本地虚拟环境，正在创建: $VENV_DIR"
  # 树莓派优先复用系统 apt 安装的 Python 包，避免在 venv 内重复编译重型依赖。
  python3 -m venv --system-site-packages "$VENV_DIR"
fi

# 确保虚拟环境内 pip 可用，自检阶段的自动安装将统一落到该环境。
"$VENV_PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true

if [[ -f "$SCRIPT_DIR/APP/pi_cli.py" ]]; then
  TARGET_SCRIPT="$SCRIPT_DIR/APP/bootstrap_entry.py"
else
  TARGET_SCRIPT="$SCRIPT_DIR/bootstrap_entry.py"
fi

exec "$VENV_PYTHON" "$TARGET_SCRIPT" "$@"
