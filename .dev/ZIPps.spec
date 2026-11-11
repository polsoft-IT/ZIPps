# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Sciezka do glownego katalogu projektu
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

# Plik wersji
version_file = os.path.join(os.path.dirname(SPEC), 'version_info.txt')

# Ikona aplikacji
icon_file = os.path.join(project_dir, 'docs', 'ico.ico')

# Dodaj gallery do danych jesli istnieje
gallery_dir = os.path.join(project_dir, 'gallery')
datas = [
    (os.path.join(project_dir, 'style.qss'), '.'),
    (os.path.join(project_dir, 'docs'), 'docs'),
]
if os.path.exists(gallery_dir):
    datas.append((gallery_dir, 'gallery'))

hidden_imports = [
    'logging',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
    'cryptography',
    'cryptography.hazmat',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.primitives.ciphers.aead',
    'zipps_pkg',
    'zipps_pkg.core',
    'zipps_pkg.settings_mod',
    'zipps_pkg.logging_mod',
    'zipps_pkg.generator',
    'zipps_pkg.packer',
    'zipps_pkg.unpacker',
    'zipps_pkg.pfa',
    'zipps_pkg.security',
    'zipps_pkg.cli',
    'zipps_pkg.gui',
    'zipps_pkg.version',
]

# Dodaj hidden imports dla opcjonalnych bibliotek tylko jesli sa dostepne
optional_libs = {
    'py7zr': ['py7zr'],
    'zstandard': ['zstandard'],
    'lz4': ['lz4', 'lz4.frame'],
    'rarfile': ['rarfile'],
    'pycdlib': ['pycdlib'],
    'brotli': ['brotli'],
    'arpy': ['arpy'],
}

for lib_name, imports in optional_libs.items():
    try:
        __import__(lib_name)
        hidden_imports.extend(imports)
    except ImportError:
        pass

a = Analysis(
    [os.path.join(project_dir, 'ZIPps.py')],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'setuptools',
        'pip',
        'wheel',
        'email',
        'html',
        'http',
        'urllib',
        'xml',
        'unittest',
        'pydoc',
        'doctest',
        'multiprocessing',
        'concurrent.futures',
        'asyncio',
        'sqlite3',
        'msvcrt',
        'win32api',
        'win32con',
        'win32gui',
        'win32com',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ZIPps',
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
    icon=icon_file if os.path.exists(icon_file) else None,
    version=version_file if os.path.exists(version_file) else None,
    onefile=True,
)
