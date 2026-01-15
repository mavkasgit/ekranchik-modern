# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\KTM\\Ekranchik-modern\\launcher\\launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\KTM\\Ekranchik-modern\\launcher\\theme.json', '.'), ('D:\\KTM\\Ekranchik-modern\\launcher\\icons.py', '.'), ('D:\\KTM\\Ekranchik-modern\\launcher\\launcher.ico', '.')],
    hiddenimports=['customtkinter', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'pystray', 'pystray._win32', 'dotenv', 'win32gui', 'win32con', 'win32process', 'win32api'],
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
    icon=['D:\\KTM\\Ekranchik-modern\\launcher\\launcher.ico'],
)
