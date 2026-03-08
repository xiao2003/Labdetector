# pi/setup.py
from pathlib import Path

from setuptools import find_namespace_packages, setup

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT.parent / "VERSION").read_text(encoding="utf-8").strip()

setup(
    name="labdetector-pi",
    version=VERSION,
    description="NeuroLab Hub Raspberry Pi edge node",
    packages=find_namespace_packages(where="."),
    py_modules=["pisend_receive", "config", "pi_cli"],
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "labdetector-pi=pi_cli:main",
        ]
    },
    install_requires=[
        "websockets>=10.0",
        "opencv-python-headless>=4.5.0",
        "numpy>=1.20.0",
        "vosk>=0.3.45",
        "pyaudio>=0.2.11",
        "pyttsx3>=2.90",
    ],
    python_requires=">=3.7",
)
