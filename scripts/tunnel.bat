@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
title SportCourts - Cloudflare Quick Tunnel
set "PORT=8000"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if /i "%%a"=="PORT" set "PORT=%%b"
    )
)

set "CF="
where cloudflared >nul 2>&1 && set "CF=cloudflared"
if not defined CF if exist "%~dp0cloudflared.exe" set "CF=%~dp0cloudflared.exe"
if not defined CF (
    echo.
    echo [ОШИБКА] Программа cloudflared не найдена.
    echo          Скачайте cloudflared-windows-amd64.exe со страницы Cloudflare, переименуйте в cloudflared.exe
    echo          и положите в папку scripts ^(или добавьте в PATH^). Подробно: docs\CLOUDFLARE.md
    echo.
    pause
    exit /b 1
)

echo ------------------------------------------------------------
echo  Запускаю временный туннель к http://127.0.0.1:%PORT%
echo  Сервер ^(scripts\start.bat^) должен быть уже запущен.
echo.
echo  Найдите в тексте ниже строку с адресом вида
echo      https://что-то-там.trycloudflare.com
echo  и вставьте его в приложении: Настройки - Сервер.
echo.
echo  Адрес МЕНЯЕТСЯ при каждом запуске туннеля, и тогда всем друзьям нужно
echo  обновить его в приложении. Пока это окно закрыто, доступа из интернета нет.
echo ------------------------------------------------------------
echo.
"%CF%" tunnel --url http://127.0.0.1:%PORT%
echo.
echo Туннель остановлен.
pause
