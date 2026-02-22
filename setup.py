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
    'Pillow>=9.0.0',  # 用于 OpenCV 中文渲染
]

# 跨平台依赖智能分发
if sys.platform.startswith('linux'):
    # 树莓派等 Linux 环境：使用 headless 版本避免 x11 依赖缺失报错
    install_requires.append('opencv-python-headless>=4.5.0')
else:
    # Windows 环境 (PC计算中枢)
    install_requires.append('opencv-python>=4.5.0')
    install_requires.append('pyttsx3>=2.90')  # Windows 默认 TTS 引擎

# ==========================================
# ★ 自定义安装引导向导 (像 Linux 一样优雅) ★
# ==========================================
# 如果用户直接运行 `python setup.py` (不带任何参数)
if len(sys.argv) == 1:
    print("=" * 60)
    print("🚀 欢迎使用 LabDetector 环境自动配置向导")
    print("=" * 60)

    current_os = "Linux / 树莓派 (无头环境)" if sys.platform.startswith('linux') else "Windows / PC (桌面环境)"
    print(f"\n🔍 检测到当前系统平台: {current_os}")
    print("\n📋 即将为您安装或更新以下核心依赖包:")

    for req in install_requires:
        print(f"  📦 {req}")

    print("\n⏳ 正在调用底层包管理器，请稍候...\n")
    print("-" * 60)

    try:
        # 在后台以开发者模式 (-e) 自动调用 pip 进行安装
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])
        print("-" * 60)
        print("\n✅ 所有环境依赖均已成功安装且处于最新状态！")
        print("💡 提示: 您现在可以直接运行 python launcher.py 启动系统。")
    except subprocess.CalledProcessError:
        print("-" * 60)
        print("\n❌ 安装过程中出现错误。请检查网络，或尝试以管理员身份运行。")

    # 拦截完毕，安全退出，不抛出 no commands supplied 错误
    sys.exit(0)

# ==========================================
# 标准的打包清单 (供 pip 底层读取使用)
# ==========================================
setup(
    name='labdetector',
    version='1.0.0',
    description='面向微纳流体实验室的多模态智能视觉管理系统',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='LabDetector Team',
    packages=find_packages(include=['pcside*', 'piside*', 'core*']),
    install_requires=install_requires,
    extras_require={
        # 语音交互扩展包
        'voice': [
            'SpeechRecognition>=3.8.1',
            'pyaudio>=0.2.11'
        ],
    },
    entry_points={
        'console_scripts': [
            'labdetector-pc=pcside.main:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    python_requires='>=3.8',
)