@echo off
REM ============================================================
REM  EmptyApp build script
REM  Requires: zig (recommended 0.13+), or python + pip install ziglang
REM  Output:   dist\EmptyApp.exe
REM
REM  NOTE: keep this file ASCII-only. A UTF-8 batch file with
REM  non-ASCII text gets mangled when cmd parses it as GBK/ANSI.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist dist mkdir dist

where zig >nul 2>nul && goto use_zig

python -c "import ziglang" >nul 2>nul && goto use_pyzig

echo [ERROR] zig compiler not found.
echo.
echo   Option 1 (recommended): winget install zig.zig
echo   Option 2             : pip install ziglang
echo.
echo Install one of them, then run this script again.
exit /b 1

:use_zig
echo [1/2] building with zig ...
zig cc -target x86_64-windows-gnu -O2 -DUNICODE -D_UNICODE "-Wl,--subsystem,windows" -s -o dist\EmptyApp.exe app.c -luser32 -lgdi32
goto check

:use_pyzig
echo [1/2] building with python -m ziglang ...
python -m ziglang cc -target x86_64-windows-gnu -O2 -DUNICODE -D_UNICODE "-Wl,--subsystem,windows" -s -o dist\EmptyApp.exe app.c -luser32 -lgdi32
goto check

:check
if errorlevel 1 (
    echo [ERROR] build failed.
    exit /b 1
)

echo [2/2] build succeeded.
for %%F in (dist\EmptyApp.exe) do echo       %%~fF  (%%~zF bytes)
echo.
echo Double-click dist\EmptyApp.exe to run.
exit /b 0
