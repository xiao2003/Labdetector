# piside/setup.py
from setuptools import setup, find_packages

setup(
    name="labdetector-pi",
    version="1.0.0",
    description="LabDetector 树莓派边缘感知端",
    packages=find_packages(),
    install_requires=[
        'websockets>=10.0',
        'opencv-python-headless>=4.5.0',
        'numpy>=1.20.0',
        'vosk>=0.3.45',
        'pyaudio>=0.2.11',
        'pyttsx3>=2.90'
    ],
    python_requires='>=3.7',
)