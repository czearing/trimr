@echo off
cd /d "%~dp0"
where python >nul 2>&1 || (echo Python 3.10 or newer is required: https://www.python.org/downloads/ & pause & exit /b 1)
python -c "import numpy, PIL" >nul 2>&1 || python -m pip install -r requirements.txt
python -m trimr %*
pause
