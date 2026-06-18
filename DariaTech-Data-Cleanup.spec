# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules('app')
    + collect_submodules('uvicorn')
    + collect_submodules('fastapi')
    + collect_submodules('starlette')
    + collect_submodules('pydantic')
    + collect_submodules('PIL')
    + collect_submodules('send2trash')
    + [
        # uvicorn runtime stack (asyncio loop + h11), forced in app/launcher.py
        'h11',
        'click',
        'anyio',
        'sniffio',
        'idna',
        'pydantic_core',
        # native folder picker used by /api/select-folder and /api/select-target
        'tkinter',
        'tkinter.filedialog',
    ]
)

a = Analysis(
    ['app/launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('web', 'web')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # optional uvicorn native deps (we force asyncio + h11 in the launcher)
        'uvloop', 'httptools', 'websockets', 'watchfiles',
        # setuptools/pkg_resources pull jaraco+backports whose runtime hook
        # crashes the frozen app on startup; nothing here needs it at runtime.
        'pkg_resources', 'setuptools', '_distutils_hack', 'jaraco', 'backports',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DariaTech-Data-Cleanup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='web/icon.ico',
    version='version_info.txt',
)
