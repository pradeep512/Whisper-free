# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Whisper-Free on macOS (Apple Silicon, arm64).

Build with:
    pyinstaller --noconfirm --clean packaging/macos/Whisper-Free.spec

Produces dist/Whisper-Free.app — a menu-bar agent app (LSUIElement=true).
Wrap in DMG via scripts/build_macos.sh (which uses create-dmg).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

assert sys.platform == 'darwin', \
    "This spec is for macOS only. Use packaging/appimage/Whisper-Free.spec on Linux."

# Resolve repo root. SPECPATH is provided by PyInstaller; spec lives in
# packaging/macos/, so parents[1] is the repo root.
ROOT = Path(SPECPATH).resolve().parents[1]

# ---------------------------------------------------------------------------
# Collect platform-specific data files and dynamic libraries.
# ---------------------------------------------------------------------------

mlx_datas = collect_data_files('mlx') + collect_data_files('mlx_whisper')
mlx_binaries = collect_dynamic_libs('mlx')

# pyobjc frameworks are dynamic — collect their dylibs.
pyobjc_binaries = (
    collect_dynamic_libs('AppKit', destdir='AppKit')
    + collect_dynamic_libs('ApplicationServices', destdir='ApplicationServices')
    + collect_dynamic_libs('AVFoundation', destdir='AVFoundation')
    + collect_dynamic_libs('ServiceManagement', destdir='ServiceManagement')
)

# App assets (icon for the bundle, menu bar template image if present).
asset_datas = [
    (str(ROOT / 'assets' / 'app-icon.png'), 'assets'),
    (str(ROOT / 'assets' / 'app-icon-512.png'), 'assets'),
]
menu_bar_icon = ROOT / 'assets' / 'menu-bar-icon.png'
if menu_bar_icon.exists():
    asset_datas.append((str(menu_bar_icon), 'assets'))

a = Analysis(
    [str(ROOT / 'app' / 'main.py')],
    pathex=[str(ROOT)],
    binaries=mlx_binaries + pyobjc_binaries,
    datas=mlx_datas + asset_datas,
    hiddenimports=[
        # pynput's Darwin (macOS Quartz) backend — PyInstaller can't always
        # resolve these via the listener factory.
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        'pynput._util.darwin',
        # mlx submodules — collect_submodules occasionally misses lazy ones.
        *collect_submodules('mlx_whisper'),
        *collect_submodules('mlx'),
        # pyobjc bindings we use.
        'AppKit',
        'ApplicationServices',
        'AVFoundation',
        'ServiceManagement',
        'objc',
        # huggingface_hub is used by mlx-whisper for model downloads.
        'huggingface_hub',
    ],
    hookspath=[str(Path(SPECPATH))],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude the entire Linux/CUDA backend to keep the bundle small.
    excludes=[
        'torch',
        'torchaudio',
        'torchvision',
        'whisper',          # openai-whisper
        'noisereduce',
        'webrtcvad',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Whisper-Free',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX is incompatible with macOS code signing & breaks Qt frameworks
    console=False,        # GUI app — no terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',  # Apple Silicon only per design Decision 2
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Whisper-Free',
)

app = BUNDLE(
    coll,
    name='Whisper-Free.app',
    icon=str(ROOT / 'assets' / 'app-icon.icns'),
    bundle_identifier='com.whisperfree.app',
    info_plist={
        'CFBundleName': 'Whisper-Free',
        'CFBundleDisplayName': 'Whisper-Free',
        'CFBundleIdentifier': 'com.whisperfree.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleExecutable': 'Whisper-Free',
        'CFBundlePackageType': 'APPL',
        'LSMinimumSystemVersion': '13.5',
        'LSApplicationCategoryType': 'public.app-category.utilities',
        # Run as a menu-bar agent (no Dock icon, no Cmd-Tab entry by default).
        # User can flip via Settings → macOS → "Show in Dock".
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
        'NSPrincipalClass': 'NSApplication',
        # Permission-prompt strings (shown by the system on first access).
        'NSMicrophoneUsageDescription':
            'Whisper-Free needs microphone access to transcribe your voice '
            'locally on this device. Nothing is sent over the network.',
        'NSAppleEventsUsageDescription':
            'Used to detect when you grant Accessibility access in '
            'System Settings.',
    },
)
