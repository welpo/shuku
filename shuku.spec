# -*- mode: python ; coding: utf-8 -*-
from os.path import join

a = Analysis(
    [join('shuku', 'cli.py')],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pysubs2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        '_bz2',
        '_hashlib',
        '_lzma',
        '_elementtree',
        '_decimal',
        '_multiprocessing',
        '_queue',
        '_wmi',
        'pyexpat',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='shuku',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
