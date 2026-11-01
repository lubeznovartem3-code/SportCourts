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
title SportCourts - сервер
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, sqlalchemy, asyncpg, alembic, PIL, argon2, jwt, dotenv, multipart" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ОШИБКА] В окружении не хватает пакетов. Запустите scripts\setup.bat - он доустановит зависимости.
    echo.
    pause
    exit /b 1
)
pushd backend
echo Проверка окружения перед запуском...
"..\.venv\Scripts\python.exe" -m app.cli check
if errorlevel 1 (
    popd
    echo.
    echo [ОШИБКА] Проверка не пройдена, сервер не запущен. Исправьте пункты [FAIL] выше
    echo          ^(подсказки: docs\TROUBLESHOOTING.md^).
    pause
    exit /b 1
)
echo.
echo ------------------------------------------------------------
echo  ВАЖНО: этот скрипт запускает ТОЛЬКО сервер ^(на этом компьютере^).
echo  Доступ из интернета ^(для друзей^) даёт отдельная программа cloudflared:
echo  запустите scripts\tunnel.bat в ДРУГОМ окне и вставьте выданный адрес
echo  в приложение ^(Настройки - Сервер^). Подробнее: docs\CLOUDFLARE.md
echo ------------------------------------------------------------
echo.
"..\.venv\Scripts\python.exe" -m app.run
set "RC=%ERRORLEVEL%"
popd
echo.
if not "%RC%"=="0" echo [ВНИМАНИЕ] Сервер завершился с кодом %RC%. Причину смотрите выше и в data\logs\sportcourts.log
if "%RC%"=="0" echo Сервер остановлен.
pause
exit /b %RC%
