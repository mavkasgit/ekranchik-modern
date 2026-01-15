# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('theme.json', '.'),
        ('icons.py', '.'),
        ('launcher.ico', '.'),
    ],
    hiddenimports=[
        'customtkinter', 
        'PIL', 
        'PIL.Image', 
        'PIL.ImageDraw', 
        'pystray', 
        'pystray._win32', 
        'dotenv', 
        'win32gui', 
        'win32con', 
        'win32process', 
        'win32api',
        'webview',
        'webview.platforms.winforms'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# Onefile - всё в одном exe
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EkranchikLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='launcher.ico',
)
