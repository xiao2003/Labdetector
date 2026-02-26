# pcside/tools/check_gpu.py
import torch
import sys

try:
    import pip
    pip_version = pip.__version__
except ImportError:
    pip_version = "未知"

print(f"    Python解释器版本: {sys.version.split(' ')[0]}")
print(f"    Python架构: {'64bit' if sys.maxsize > 2**32 else '32bit'}")
print(f"    操作系统: {sys.platform}")
print(f"    pip版本: {pip_version}")
print(f"    PyTorch 版本: {torch.__version__}")

# ★ 极限防崩溃拦截：某些纯 CPU 版本的 PyTorch 连调用 torch.cuda 都会抛出 AssertionError
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
    except Exception as e:
        print(f"[WARN] 无法获取 GPU 详细参数: {e}")
else:
    print("\n[WARN] 未检测到支持 CUDA 的显卡，或当前安装的是 CPU 版 PyTorch！")
    print("[INFO] AI 视觉推理将退化至 CPU 计算，这可能导致严重的卡顿。")
    print("[INFO] 建议使用以下命令重装 GPU 版本:")
    print("       pip uninstall torch torchvision torchaudio -y")
    print("       pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu129")
    print(" [INFO] 如遇下载速度慢可直接VPN下载如下版本")
    print("       https://download.pytorch.org/whl/cu129/torch-2.8.0%2Bcu129-cp311-cp311-win_amd64.whl")
    print(r"       安装指令为C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe -m pip install 下载文件的路径")
