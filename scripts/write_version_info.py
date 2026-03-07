#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write the Windows version resource file used by PyInstaller."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc.app_identity import APP_NAME, COMPANY_NAME_EN, COPYRIGHT_TEXT_EN
from pc.tools.version_manager import get_app_version

OUTPUT_PATH = PROJECT_ROOT / 'scripts' / 'version_info.txt'


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = []
    for raw in version.split('.'):
        digits = ''.join(ch for ch in raw if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def main() -> None:
    version = get_app_version()
    filevers = version_tuple(version)
    content = f'''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers},
    prodvers={filevers},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'080404B0',
        [
          StringStruct(u'CompanyName', u'{COMPANY_NAME_EN}'),
          StringStruct(u'FileDescription', u'LabDetector Intelligent Laboratory Desktop Suite'),
          StringStruct(u'FileVersion', u'{version}'),
          StringStruct(u'InternalName', u'{APP_NAME}'),
          StringStruct(u'LegalCopyright', u'{COPYRIGHT_TEXT_EN}'),
          StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
          StringStruct(u'ProductName', u'{APP_NAME}'),
          StringStruct(u'ProductVersion', u'{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
'''
    OUTPUT_PATH.write_text(content, encoding='utf-8')
    print(f'Wrote {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
