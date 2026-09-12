# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds "SMTC Bridge.app" (menu bar only, no Dock icon).
from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "SMTC Bridge"
BUNDLE_ID = "gg.nutty.smtc-bridge"
VERSION = "1.0.0"

datas = [
    ("vendor/mediaremote-adapter", "vendor/mediaremote-adapter"),
    ("assets/menubar.png", "assets"),
    ("assets/menubar@2x.png", "assets"),
]
hiddenimports = collect_submodules("rumps") + ["flask_cors"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon="assets/icon.icns",
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,           # menu bar app: no Dock icon, no app switcher entry
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "nutty",
    },
)
