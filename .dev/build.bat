@echo off
chcp 65001 >nul
echo ========================================
echo   ZIPps - Build Script v2.7.0
echo ========================================
echo.

cd /d %~dp0..

echo [1/5] Checking PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
) else (
    echo PyInstaller found.
)

echo.
echo [2/5] Checking dependencies...
python -m pip show PySide6 >nul 2>&1
if errorlevel 1 (
    echo Installing PySide6...
    python -m pip install PySide6
)

python -m pip show cryptography >nul 2>&1
if errorlevel 1 (
    echo Installing cryptography...
    python -m pip install cryptography
)

echo.
echo [3/5] Cleaning old build/dist folders...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [4/5] Compiling to EXE...
python -m PyInstaller --clean .dev\ZIPps.spec

if errorlevel 1 (
    echo.
    echo ERROR: Compilation failed
    pause
    exit /b 1
)

echo.
echo [5/5] Copying to .dev\dist...
if not exist .dev\dist mkdir .dev\dist
copy /Y dist\ZIPps.exe .dev\dist\ZIPps.exe

echo.
echo Cleaning builder files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo ========================================
echo   Compilation completed successfully!
echo ========================================
echo.
echo EXE file: .dev\dist\ZIPps.exe
echo.

pause
