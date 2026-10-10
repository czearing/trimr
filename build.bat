@echo off
rem Builds reducer\build\Release\trimr-reduce.exe. Needs Visual Studio Build Tools (C++) and CMake.
call "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
cmake -S reducer -B reducer\build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=cl || exit /b 1
cmake --build reducer\build || exit /b 1
echo Built reducer\build\trimr-reduce.exe
