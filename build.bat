@echo off
REM PaintMaster Pro - bouwscript (Windows). Vereist Python 3.10+ (https://python.org, vink "Add to PATH" aan).
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv || python -m venv .venv )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :err
python make_icon.py || goto :err
pyinstaller --noconfirm --clean --onefile --windowed --name PaintMasterPro --icon assets\icon.ico --add-data "assets;assets" --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQml --exclude-module PySide6.Qt3DCore main.py || goto :err
echo.
echo Klaar! Je programma staat in: dist\PaintMasterPro.exe
pause
exit /b 0
:err
echo.
echo FOUT tijdens bouwen. Zie de melding hierboven.
pause
exit /b 1
