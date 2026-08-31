# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the MAS AI Orchestrator desktop app.

Run from the repo root with:
    pyinstaller desktop_app/packaging/mas_ai_orchestrator.spec

Produces a one-directory build (not --onefile): a single-file .exe would
have to unpack uiautomator2/opencv/torch-scale dependencies to a temp
directory on every launch, which is slow for an app this size. One-directory
keeps startup fast at the cost of shipping a folder instead of one file --
acceptable since QA installs this once, not a link people click each time.
"""

import os

block_cipher = None

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), "..", ".."))

a = Analysis(
    [os.path.join(PROJECT_ROOT, "desktop_app", "app.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, "desktop_app", "vendor", "platform-tools"), "desktop_app/vendor/platform-tools"),
    ],
    hiddenimports=[
        "nicegui",
        "uiautomator2",
        "adbutils",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MAS AI Orchestrator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="MAS AI Orchestrator",
)
