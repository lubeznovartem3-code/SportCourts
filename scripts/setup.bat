@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
echo ============================================================
echo  SportCourts - первичная настройка сервера
echo ============================================================
echo.

set "PY="
rem Предпочитаем версию, на которой проект проверялся (3.13), затем 3.12, затем любой Python 3.
py -3.13 --version >nul 2>&1 && set "PY=py -3.13"
if not defined PY py -3.12 --version >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    echo [ОШИБКА] Python не найден. Установите Python 3.13 с python.org ^(рядом с имеющимся, старый удалять не нужно^)
    echo          и отметьте галочку "Add python.exe to PATH". См. README, раздел "Версия Python".
    pause
    exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)"
if errorlevel 1 (
    echo [ОШИБКА] Нужен Python 3.12 или новее. См. README, раздел "Версия Python".
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PY% --version') do echo Найден: %%v

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Создаю виртуальное окружение .venv ^(ваш системный Python не изменяется^)...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
)

echo.
echo Устанавливаю зависимости сервера ^(нужен интернет, 1-3 минуты^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости. Если в тексте выше есть "no matching distribution"
    echo          или "failed building wheel" - у вас слишком новый или слишком старый Python для этих пакетов.
    echo          Установите Python 3.12 или 3.13 и повторите ^(см. docs\TROUBLESHOOTING.md^).
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo ------------------------------------------------------------
    echo  Создан файл .env из примера. ОТКРОЙТЕ его в Блокноте и:
    echo    1. впишите пароль пользователя sportcourts в DATABASE_URL;
    echo    2. замените SECRET_KEY на случайную строку, получить её можно командой:
    echo       .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
    echo  Затем запустите scripts\setup.bat ещё раз.
    echo ------------------------------------------------------------
    pause
    exit /b 0
)

echo.
echo Применяю миграции базы данных...
pushd backend
"..\.venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
    popd
    echo.
    echo [ОШИБКА] Не удалось применить миграции. Проверьте, что PostgreSQL запущен, база создана
    echo          ^(docs\POSTGRESQL.md^) и DATABASE_URL в .env верен.
    pause
    exit /b 1
)
echo.
echo Проверка окружения:
"..\.venv\Scripts\python.exe" -m app.cli check
popd
echo.
echo Готово. Дальше: scripts\create-admin.bat ^(один раз^), затем scripts\start.bat
pause
