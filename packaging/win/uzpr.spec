# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path

block_cipher = None
src = Path("src")

# Only include data directories that actually exist at build time
_candidate_datas = [
    (str(src / "uzpr" / "ui" / "assets"), "uzpr/ui/assets"),
    ("packaging/rules", "packaging/rules"),
    ("packaging/wordlists", "packaging/wordlists"),
]
datas = [(s, d) for s, d in _candidate_datas if Path(s).exists()]

a = Analysis(
    [str(src / "uzpr" / "__main__.py")],
    pathex=[str(src)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        "PySide6.QtSvg",
        "PySide6.QtXml",
        "PySide6.QtOpenGL",
        "qfluentwidgets",
        "blake3",
        "structlog",
        "platformdirs",
        "httpx",
        "sqlmodel",
        "sqlalchemy",
        "cryptography",
        "pyzipper",
        "rarfile",
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
