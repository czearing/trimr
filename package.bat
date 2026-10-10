@echo off
rem Builds dist\Trimr-<version>.zip from a built reducer. Run build.bat first.
if not exist reducer\build\trimr-reduce.exe (echo Run build.bat first & exit /b 1)
if exist dist rmdir /s /q dist
mkdir dist\Trimr
copy reducer\build\trimr-reduce.exe dist\Trimr\ >nul
xcopy trimr dist\Trimr\trimr\ /E /I /Q /EXCLUDE:package.exclude >nul
copy Trimr.bat dist\Trimr\ >nul
copy requirements.txt dist\Trimr\ >nul
copy README.md dist\Trimr\ >nul
copy LICENSE dist\Trimr\ >nul
for /f %%v in ('python -c "from trimr import __version__ as v; print(v)"') do set VER=%%v
powershell -NoProfile -Command "Compress-Archive -Path dist\Trimr -DestinationPath dist\Trimr-%VER%.zip -Force"
echo Built dist\Trimr-%VER%.zip
