@echo off
chcp 65001 >nul
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 pip install pyinstaller -q
pip install -r requirements.txt -q
pyinstaller ^
    --onefile ^
    --console ^
    --icon=icon.ico ^
    --name "Command Server Launcher" ^
    --add-data "launcher;launcher" ^
    --hidden-import launcher.logger ^
    --hidden-import launcher.config ^
    --hidden-import launcher.login ^
    --hidden-import launcher.minecraft ^
    --hidden-import launcher.modpack ^
    --hidden-import launcher.launch ^
    --hidden-import launcher.downloader ^
    --hidden-import launcher.network ^
    --hidden-import urllib.request ^
    --hidden-import urllib.parse ^
    --hidden-import urllib.error ^
    --hidden-import requests ^
    --hidden-import urllib3 ^
    main.py 
rmdir /s /q "build" >nul
del /q "*.spec" >nul
pause >nul