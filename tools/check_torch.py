import torch

# 基础信息
print(f"PyTorch版本: {torch.__version__}")
print(f"CUDA是否可用: {torch.cuda.is_available()}")

# CUDA详细信息（有GPU时）
if torch.cuda.is_available():
    print(f"CUDA版本: {torch.version.cuda}")
    print(f"GPU数量: {torch.cuda.device_count()}")
    print(f"当前GPU: {torch.cuda.get_device_name(0)}")
else:
    print("未检测到CUDA，使用CPU运行")
    print("如果需要GPU加速，请安装带CUDA的PyTorch版本")