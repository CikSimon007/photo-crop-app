@echo off
REM Build script for Windows
REM Usage: build.bat

echo === Orezavanie fotiek pre tlac - Build ===

pip install -r requirements.txt

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "Orezavanie-fotiek" ^
    --noconfirm ^
    main.py

echo.
echo Build hotovy!
echo Subor: dist\Orezavanie-fotiek.exe
pause
