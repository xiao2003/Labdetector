from __future__ import annotations

import importlib
import sys


try:
    import pip

    pip_version = pip.__version__
except Exception:
    pip_version = "unknown"

print(f"    Python 解释器版本: {sys.version.split(' ')[0]}")
print(f"    Python 架构: {'64bit' if sys.maxsize > 2**32 else '32bit'}")
print(f"    操作系统: {sys.platform}")
print(f"    pip 版本: {pip_version}")

try:
    torch = importlib.import_module("torch")
except Exception:
    print("[WARN] 未检测到 PyTorch，当前发布版已按轻量模式构建。")
    print("[INFO] 如需 GPU 推理或本地视觉模型，请在专家模型管理中导入对应依赖包。")
    raise SystemExit(0)

print(f"    PyTorch 版本: {torch.__version__}")

try:
    cuda_version = torch.version.cuda
    is_cuda_avail = torch.cuda.is_available()
except Exception:
    cuda_version = "None"
    is_cuda_avail = False

print(f"    CUDA 版本: {cuda_version}")
print(f"    GPU 可用: {is_cuda_avail}")

if is_cuda_avail:
    try:
        print(f"    GPU 名称: {torch.cuda.get_device_name(0)}")
        print(f"    CUDA 算力: {torch.cuda.get_device_capability(0)}")
    except Exception as exc:
        print(f"[WARN] 无法获取 GPU 详细参数: {exc}")
else:
    print("[WARN] 未检测到可用 CUDA，将自动降级为 CPU 或云端推理。")
