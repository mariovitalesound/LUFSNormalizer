@echo off
echo ====================================================
echo LUFS Normalizer v3.0.3 - Build Script
echo ====================================================
echo.

echo Installing dependencies...
pip install --upgrade pyinstaller Pillow PySide6

echo.
echo Generating application icon...
python create_icon.py

echo.
echo Building executable...
pyinstaller --onefile --windowed ^
    --name "LUFSNormalizer_v3.0.3" ^
    --icon "app_icon.ico" ^
    --add-data "config.default.json;." ^
    --add-data "lufs_normalizer;lufs_normalizer" ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=soundfile ^
    --hidden-import=pyloudnorm ^
    --hidden-import=soxr ^
    --hidden-import=numpy ^
    --hidden-import=watchdog ^
    --exclude-module=PySide6.QtWebEngine ^
    --exclude-module=PySide6.Qt3D ^
    --exclude-module=PySide6.QtMultimedia ^
    --exclude-module=PySide6.QtQuick ^
    --exclude-module=customtkinter ^
    --exclude-module=tkinter ^
    normalize_gui_modern.py

echo.
echo Creating distribution package...
if not exist "dist\LUFSNormalizer_v3.0.3" mkdir "dist\LUFSNormalizer_v3.0.3"

move "dist\LUFSNormalizer_v3.0.3.exe" "dist\LUFSNormalizer_v3.0.3\"
copy "config.default.json" "dist\LUFSNormalizer_v3.0.3\config.json"
copy "verify_audio.py" "dist\LUFSNormalizer_v3.0.3\"
if exist "app_icon.ico" copy "app_icon.ico" "dist\LUFSNormalizer_v3.0.3\"
if exist "taskbar_icon.ico" copy "taskbar_icon.ico" "dist\LUFSNormalizer_v3.0.3\"

echo.
echo ====================================================
echo BUILD COMPLETE!
echo ====================================================
echo Distribution: dist\LUFSNormalizer_v3.0.3\
echo ====================================================
pause
