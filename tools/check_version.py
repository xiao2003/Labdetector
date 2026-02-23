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