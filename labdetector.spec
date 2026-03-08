# -*- mode: python ; coding: utf-8 -*-

import os


hiddenimports = [
    "pc.desktop_app",
    "pc.main",
    "pc.webui.runtime",
    "pc.webui.server",
    "pc.voice.voice_interaction",
    "pc.communication.multi_ws_manager",
    "pc.communication.network_scanner",
    "pc.core.scheduler_manager",
    "pc.core.tts",
    "pc.core.expert_manager",
    "pc.core.expert_registry",
    "pc.core.subprocess_utils",
    "pc.knowledge_base.rag_engine",
    "pc.knowledge_base.structured_kb",
    "pc.knowledge_base.media_ingestion",
    "pc.tools.model_downloader",
    "pc.tools.version_manager",
    "pc.tools.check_gpu",
    "pc.tools.check_mic",
    "pc.experts.equipment_ocr_expert",
    "pc.experts.lab_qa_expert",
    "pc.experts.nanofluidics.microfluidic_contact_angle_expert",
    "pc.experts.nanofluidics.nanofluidics_multimodel_expert",
    "pc.experts.nanofluidics.nanofluidics_models",
    "pc.experts.safety.chem_safety_expert",
    "pc.experts.safety.equipment_operation_expert",
    "pc.experts.safety.flame_fire_expert",
    "pc.experts.safety.general_safety_expert",
    "pc.experts.safety.hand_pose_expert",
    "pc.experts.safety.integrated_lab_safety_expert",
    "pc.experts.safety.ppe_expert",
    "pc.experts.safety.semantic_risk_mapper",
    "pc.experts.safety.spill_detection_expert",
]

icon_file = os.path.join("assets", "branding", "labdetector.ico")
version_file = os.path.join("scripts", "version_info.txt")

datas = [
    ("config.ini", "pc"),
    ("VERSION", "pc"),
    ("pc/webui/static", "pc/pc/webui/static"),
    ("assets/branding", "pc/assets/branding"),
    ("docs", "pc/docs"),
]

if os.path.exists("pc/knowledge_base/docs"):
    datas.append(("pc/knowledge_base/docs", "pc/pc/knowledge_base/docs"))
if os.path.exists("pc/knowledge_base/structured_kb.sqlite3"):
    datas.append(("pc/knowledge_base/structured_kb.sqlite3", "pc/pc/knowledge_base"))
if os.path.exists("pc/knowledge_base/scopes"):
    datas.append(("pc/knowledge_base/scopes", "pc/pc/knowledge_base/scopes"))
if os.path.exists("pc/voice/model"):
    datas.append(("pc/voice/model", "pc/pc/voice/model"))
if os.path.exists("pc/tools/VERSION"):
    datas.append(("pc/tools/VERSION", "pc/pc/tools"))

excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "easyocr",
    "mediapipe",
    "langchain",
    "langchain_classic",
    "langchain_community",
    "langchain_core",
    "langchain_huggingface",
    "langchain_text_splitters",
    "sentence_transformers",
    "transformers",
    "faiss",
    "faiss_cpu",
    "modelscope",
    "ultralytics",
]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="NeuroLab Hub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=icon_file if os.path.exists(icon_file) else None,
    version=version_file if os.path.exists(version_file) else None,
    contents_directory="APP",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="NeuroLab Hub",
)