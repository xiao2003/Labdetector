# -*- mode: python ; coding: utf-8 -*-

import os

icon_file = os.path.join("assets", "branding", "neurolab_hub.ico")
version_file = os.path.join("scripts", "version_info.txt")
exe_name = os.environ.get("NEUROLAB_EXE_NAME", "NeuroLab Hub")

excludes = [
    "cv2",
    "numpy",
    "PIL",
    "torch",
    "torchaudio",
    "funasr",
    "modelscope",
    "transformers",
    "datasets",
    "peft",
    "ultralytics",
    "easyocr",
    "mediapipe",
    "langchain",
    "langchain_classic",
    "langchain_community",
    "langchain_core",
    "langchain_huggingface",
    "langchain_text_splitters",
    "sentence_transformers",
    "faiss",
    "faiss_cpu",
]

a = Analysis(
    ["bootstrap_entry.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=icon_file if os.path.exists(icon_file) else None,
    version=version_file if os.path.exists(version_file) else None,
)
