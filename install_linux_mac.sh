#!/usr/bin/env bash
set -e

echo "============================================================"
echo " PhotoVault — Linux / macOS Installer"
echo "============================================================"
echo

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+."
    exit 1
fi

PYTHON=$(command -v python3)
echo "Using Python: $($PYTHON --version)"
echo

# Base dependencies
echo "Installing base dependencies..."
$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install PyQt6 Pillow imagehash exifread numpy scipy
echo
echo "Base install complete."
echo

# macOS: PyQt6 may need extra steps
if [[ "$(uname)" == "Darwin" ]]; then
    echo "macOS detected."
    if ! command -v brew &>/dev/null; then
        echo "Tip: Install Homebrew for easier dependency management."
    fi
fi

# Face recognition (optional)
echo "============================================================"
echo " OPTIONAL: Face Recognition"
echo " Requires build tools (cmake, gcc/clang)."
echo "============================================================"
read -p "Install face recognition? [y/N]: " INSTALL_FACE
if [[ "$INSTALL_FACE" =~ ^[Yy]$ ]]; then
    if [[ "$(uname)" == "Darwin" ]]; then
        brew install cmake || true
    else
        sudo apt-get install -y cmake build-essential 2>/dev/null || true
    fi
    $PYTHON -m pip install cmake dlib face-recognition
    echo "Face recognition installed."
fi

echo
echo "============================================================"
echo " Installation complete!"
echo " Run PhotoVault with:   python3 main.py"
echo "============================================================"
