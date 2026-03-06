# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('pcside.experts')
hiddenimports += collect_submodules('pcside.knowledge_base')
hiddenimports += collect_submodules('pcside.voice')
hiddenimports += collect_submodules('pcside.communication')
hiddenimports += collect_submodules('pcside.core')

icon_file = os.path.join('assets', 'branding', 'labdetector.ico')
version_file = os.path.join('scripts', 'version_info.txt')

datas = [
    ('config.ini', '.'),
    ('VERSION', '.'),
    ('pcside/webui/static', 'pcside/webui/static'),
    ('assets/branding', 'assets/branding'),
    ('docs', 'docs'),
]

if os.path.exists('pcside/knowledge_base/docs'):
    datas.append(('pcside/knowledge_base/docs', 'pcside/knowledge_base/docs'))
if os.path.exists('pcside/knowledge_base/faiss_index'):
    datas.append(('pcside/knowledge_base/faiss_index', 'pcside/knowledge_base/faiss_index'))
if os.path.exists('pcside/knowledge_base/structured_kb.sqlite3'):
    datas.append(('pcside/knowledge_base/structured_kb.sqlite3', 'pcside/knowledge_base'))
if os.path.exists('pcside/knowledge_base/scopes'):
    datas.append(('pcside/knowledge_base/scopes', 'pcside/knowledge_base/scopes'))

if os.path.exists('pcside/voice/model'):
    datas.append(('pcside/voice/model', 'pcside/voice/model'))
if os.path.exists('pcside/tools/VERSION'):
    datas.append(('pcside/tools/VERSION', 'pcside/tools'))

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LabDetector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=icon_file if os.path.exists(icon_file) else None,
    version=version_file if os.path.exists(version_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='LabDetector',
)
