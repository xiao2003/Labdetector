from setuptools import setup, find_packages

setup(
    name="labdetector",
    version="2.0.0",
    description="智能多模态实验室管家 (RAG + 边缘计算版)",
    author="Xiao",
    packages=find_packages(),
    install_requires=[
        line.strip() for line in open("requirements.txt").readlines()
        if line.strip() and not line.startswith("#")
    ],
    python_requires=">=3.9",
)