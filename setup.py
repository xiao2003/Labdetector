from __future__ import annotations

from pathlib import Path
import json

from setuptools import find_packages, setup

PROJECT_ROOT = Path(__file__).resolve().parent
IDENTITY = json.loads((PROJECT_ROOT / "project_identity.json").read_text(encoding="utf-8"))

setup(
    name="neurolab-hub",
    version="1.0.0",
    description=IDENTITY["formal_name"],
    author=IDENTITY["company_name_en"],
    packages=find_packages(),
    install_requires=[
        line.strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ],
    python_requires=">=3.11",
)
