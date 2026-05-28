# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_data_files
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]

whisper_datas = collect_data_files('whisper')
notice_datas = [
    (str(ROOT / 'THIRD_PARTY_NOTICES.md'), 'licenses'),
    (str(ROOT / 'licenses' / 'README.md'), 'licenses'),
    (str(ROOT / 'licenses' / 'LGPL-3.0.txt'), 'licenses'),
    (str(ROOT / 'licenses' / 'GPL-3.0.txt'), 'licenses'),
]

a = Analysis(
    [str(ROOT / 'app' / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=whisper_datas + notice_datas,
    hiddenimports=[
        'pynput.keyboard._xorg',
        'pynput.mouse._xorg',
        'pynput._util.xorg',
        'pynput._util.xorg_keysyms',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='Whisper-Free',
)
