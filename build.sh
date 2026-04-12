#!/bin/bash
# Build script for macOS / Linux
# Usage: ./build.sh

set -e

echo "=== Orezavanie fotiek pre tlac - Build ==="

# Install dependencies
pip install -r requirements.txt

# Build with PyInstaller
pyinstaller \
    --onedir \
    --windowed \
    --name "Orezavanie-fotiek" \
    --noconfirm \
    main.py

echo ""
echo "Build hotovy!"
echo "Aplikacia sa nachadza v: dist/Orezavanie-fotiek/"

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "macOS .app: dist/Orezavanie-fotiek.app"
fi
