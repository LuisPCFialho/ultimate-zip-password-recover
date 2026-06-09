# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
src = Path("src")

a = Analysis(
    [str(src / "uzpr" / "__main__.py")],
    pathex=[str(src)],
    binaries=[],
    datas=[
        (str(src / "uzpr" / "ui" / "assets"), "uzpr/ui/assets"),
        ("packaging/rules", "packaging/rules"),
        ("packaging/wordlists", "packaging/wordlists"),
    ],
    hiddenimports=[
        "qfluentwidgets",
        "PySide6.QtSvg",
        "PySide6.QtXml",
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        "blake3",
        "py_cpuinfo",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="UltimateZipPasswordRecover",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="packaging/win/uzpr.ico",
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True,
    upx_exclude=[], name="UltimateZipPasswordRecover"
)
