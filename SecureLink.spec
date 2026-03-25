# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path.cwd()


a = Analysis(
    ['seclink_main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ('README.md', '.'),
    ],
    hiddenimports=['customtkinter', 'PIL', 'cryptography'],
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
    name='SecureLink',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SecureLink',
)
