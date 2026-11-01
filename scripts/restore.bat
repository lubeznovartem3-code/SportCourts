@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ОШИБКА] Не найдено виртуальное окружение. Сначала запустите scripts\setup.bat
    echo.
    if not "%~1"=="--scheduled" pause
    exit /b 1
)
if not exist ".env" (
    echo.
    echo [ОШИБКА] Нет файла .env. Запустите scripts\setup.bat - он создаст его из .env.example.
    echo.
    if not "%~1"=="--scheduled" pause
    exit /b 1
)
pushd backend
if "%~1"=="" (
    echo Доступные резервные копии:
    echo.
    "..\.venv\Scripts\python.exe" -m app.backup list
    echo.
    echo Запустите снова с именем копии, например:
    echo     scripts\restore.bat sportcourts_20260101_040000
    popd
    pause
    exit /b 1
)
"..\.venv\Scripts\python.exe" -m app.backup restore %1
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
