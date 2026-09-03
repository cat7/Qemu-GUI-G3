# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Qemu-GUI. Not run as part of the build here; the user
# packages with:   pyinstaller --noconfirm QemuGUI.spec
# (equivalent to: pyinstaller --onedir --windowed --noconfirm qemu_gui.py)
# Put the resulting dist/QemuGUI folder next to qemu-system-ppc so the QEMU
# folder is auto-discovered, or set it under File > Settings.

a = Analysis(
    ['qemu_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.filedialog',
                   'tkinter.messagebox', 'tkinter.simpledialog'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QemuGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='QemuGUI',
)
app = BUNDLE(
    coll,
    name='QemuGUI.app',
    icon=None,
    bundle_identifier='org.cat7.qemu-gui',
)
