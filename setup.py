#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import sys
import os
import subprocess

# 读取 README 作为长描述
here = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = "面向微纳流体实验室的多模态智能视觉管理系统"

# 核心基础依赖
install_requires = [
    'numpy>=1.20.0',
    'requests>=2.25.0',
    'websockets>=10.0',
    'Pillow>=9.0.0',
    'opencv-python>=4.5.0',
]

# 针对 Windows 端特有的依赖
if not sys.platform.startswith('linux'):
    install_requires.append('pyttsx3>=2.90')

# ==========================================
# ★ 自动化安装引导逻辑 ★
# ==========================================
# 当用户直接运行 python setup.py 时，自动执行开发者模式安装
if len(sys.argv) <= 1 or sys.argv[1] == 'install':
    print("=" * 60)
    print("🚀 正在为您初始化实验室 AI 助手开发环境...")
    print("正在执行: pip install -e .")
    try:
        # 使用开发者模式 (-e) 安装，这样修改代码后无需重新安装即可生效
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])
        print("\n✅ 环境依赖与项目模块已成功注册！")
        print("💡 现在您可以使用 'from pcside.core.config import ...' 进行跨文件夹调用了。")
        print("-" * 60)
    except subprocess.CalledProcessError:
        print("\n❌ 安装失败，请检查网络或尝试使用管理员/sudo权限运行。")
    sys.exit(0)

# ==========================================
# 标准打包配置
# ==========================================
setup(
    name='labdetector',
    version='1.0.0',
    description='面向微纳流体实验室的多模态智能视觉管理系统',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='LabDetector Team',
    # ★ 核心修正：自动发现所有以 pcside 或 piside 开头的包 ★
    # 这会确保 pcside.core 和 pcside.communication 都能被正确识别
    packages=find_packages(include=['pcside', 'pcside.*', 'piside', 'piside.*']),
    install_requires=install_requires,
    python_requires='>=3.8',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
    ],
)