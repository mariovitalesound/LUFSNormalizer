@echo off
echo ====================================================
echo LUFS Normalizer v2.4.2 - Build Script
echo ====================================================
echo.

echo Installing dependencies...
pip install --upgrade pyinstaller Pillow

echo.
echo Generating application icon...
python create_icon.py

echo.
echo Building executable...
pyinstaller --onefile --windowed ^
    --name "LUFSNormalizer_v2.4.2" ^
    --icon "lufs_icon.ico" ^
    --add-data "config.json;." ^
    --hidden-import=customtkinter ^
    --hidden-import=soundfile ^
    --hidden-import=pyloudnorm ^
    --hidden-import=soxr ^
    --hidden-import=numpy ^
    normalize_gui_modern.py

echo.
echo Creating distribution package...
if not exist "dist\LUFSNormalizer_v2.4.2" mkdir "dist\LUFSNormalizer_v2.4.2"

move "dist\LUFSNormalizer_v2.4.2.exe" "dist\LUFSNormalizer_v2.4.2\"
copy "config.json" "dist\LUFSNormalizer_v2.4.2\"
copy "verify_audio.py" "dist\LUFSNormalizer_v2.4.2\"
copy "RELEASE_NOTES_v2.4.2.txt" "dist\LUFSNormalizer_v2.4.2\"
copy "lufs_icon.ico" "dist\LUFSNormalizer_v2.4.2\"

echo.
echo ====================================================
echo BUILD COMPLETE!
echo ====================================================
echo Distribution: dist\LUFSNormalizer_v2.4.2\
echo ====================================================
pause
