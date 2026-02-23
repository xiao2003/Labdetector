import torch
import platform
import sys

# 查看Python版本（含详细信息）
print(f"Python解释器版本: {sys.version}")
print(f"Python架构（32/64位）: {platform.architecture()[0]}")
print(f"操作系统: {platform.system()} {platform.release()}")

# 查看pip版本（用于安装包）
try:
    import pip
    print(f"pip版本: {pip.__version__}")
except ImportError:
    print("未检测到pip，请先安装pip")
# 1. 检查版本
print(f"PyTorch 版本: {torch.__version__}")
print(f"CUDA 版本: {torch.version.cuda}")

# 2. 检查支持的架构 (关键!)
print(f"支持的架构: {torch.cuda.get_arch_list()}")

# 3. 检查 GPU 是否可用
print(f"GPU 可用: {torch.cuda.is_available()}")
print(f"GPU 名称: {torch.cuda.get_device_name(0)}")

if torch.cuda.is_available():
    print(f"GPU数量: {torch.cuda.device_count()}")
    print(f"当前GPU: {torch.cuda.get_device_name(0)}")
else:
    print("未检测到CUDA，使用CPU运行")
    print("如果需要GPU加速，请安装带CUDA的PyTorch版本")

# 4. 简单计算测试
x = torch.randn(1000, 1000).cuda()
y = x @ x
print(f"计算测试通过! 结果形状: {y.shape}")
