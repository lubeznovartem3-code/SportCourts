@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
echo Создаю ежедневное задание Планировщика Windows "SportCourts backup" на 04:00.
echo Компьютер в это время должен быть включён ^(если он спит или выключен - копия не создастся^).
echo.
schtasks /Create /TN "SportCourts backup" /TR "\"%~dp0backup.bat\" --scheduled" /SC DAILY /ST 04:00 /F
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось создать задание. Запустите этот файл от имени администратора ^(правый клик - Запуск от имени администратора^).
) else (
    echo.
    echo Готово. Проверить: Планировщик заданий - "SportCourts backup". Удалить: schtasks /Delete /TN "SportCourts backup" /F
    echo Проверьте результат после первой ночи командой scripts\backup.bat или в папке с копиями.
)
pause
