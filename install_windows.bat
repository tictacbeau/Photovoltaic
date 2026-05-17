@echo off
echo ============================================================
echo  PhotoVault - Windows Installer
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Install base dependencies
echo Installing base dependencies...
pip install PyQt6 Pillow imagehash exifread numpy scipy
if errorlevel 1 (
    echo ERROR: Failed to install base dependencies.
    pause
    exit /b 1
)
echo.
echo Base install complete.
echo.

:: Face recognition (optional)
echo ============================================================
echo  OPTIONAL: Face Recognition
echo  This requires cmake and Visual Studio Build Tools.
echo  Skip if you don't need facial recognition.
echo ============================================================
echo.
set /p INSTALL_FACE="Install face recognition? (y/N): "
if /i "%INSTALL_FACE%"=="y" (
    echo Installing cmake...
    pip install cmake
    echo Installing dlib (this may take several minutes)...
    pip install dlib
    echo Installing face-recognition...
    pip install face-recognition
    echo Face recognition installed.
)

echo.
echo ============================================================
echo  Installation complete!
echo  Run PhotoVault with:   python main.py
echo ============================================================
pause
