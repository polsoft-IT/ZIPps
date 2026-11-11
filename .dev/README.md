# ZIPps - Development Build Files

This folder contains files for building the ZIPps executable (.exe) on Windows.

## Files

### ZIPps.spec
PyInstaller specification file for compiling ZIPps into a single executable.
- Includes style.qss, docs folder, and gallery folder (if exists)
- Hidden imports for PySide6, cryptography, and optional compression libraries (auto-detected)
- Excludes unnecessary Python modules to reduce file size

### build.bat
Windows batch script to build ZIPps.exe automatically.
- Checks and installs PyInstaller, PySide6, cryptography
- Cleans old build/dist folders
- Runs PyInstaller with the spec file using `python -m PyInstaller`
- Copies the output to `.dev\dist\ZIPps.exe`
- Usage: Run from project root or double-click the .bat file

### create_bat.vbs
VBScript helper to create build.bat with proper encoding.
- Run this if build.bat has encoding issues

### version_info.txt
Version information for the Windows executable (embedded in EXE).
- Company: polsoft.ITS™
- Product: Pro File Packer Enterprise
- Version: 2.7.0.0
- Copyright: © 2024 Sebastian Januchowski

### dist/
Output folder for the compiled executable.
- Contains `ZIPps.exe` after successful build

## Building ZIPps.exe

1. Ensure Python 3.8+ is installed
2. Run `build.bat` from the project root
3. The executable will be created in `.dev\dist\ZIPps.exe`

## Optional Dependencies

The following libraries are optional but supported if installed:

**Core:**
- `cryptography` - for encryption (AES-256 ZIP, PFA encryption)

**Archive formats:**
- `py7zr` - for .7z archives (requires Visual C++ Build Tools on Windows)
- `zstandard` - for .zst and .tar.zst archives
- `lz4` - for .lz4 and .tar.lz4 archives
- `brotli` - for .br and .tar.br archives
- `rarfile` - for .rar archives (read-only)
- `pycdlib` - for .iso archives (read-only)
- `arpy` - for .ar archives

Install with:
```bash
pip install cryptography zstandard lz4 brotli rarfile pycdlib arpy
```

**Note:** py7zr requires Microsoft Visual C++ 14.0 or greater on Windows. If you don't have Visual Studio installed, you can install the build tools from: https://visualstudio.microsoft.com/visual-cpp-build-tools/

The build script does NOT automatically install py7zr due to these build requirements. Install it manually if you need .7z support.
