from setuptools import setup, find_packages

setup(
    name="neurolab-hub",
    version="3.0.6",
    description="NeuroLab Hub intelligent laboratory desktop suite",
    author="NeuroLab Hub Software Team",
    packages=find_packages(),
    install_requires=[
        line.strip() for line in open("requirements.txt", encoding="utf-8").readlines()
        if line.strip() and not line.startswith("#")
    ],
    python_requires=">=3.11",
)