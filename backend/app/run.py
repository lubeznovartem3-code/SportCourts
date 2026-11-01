"""Запуск сервера: `python -m app.run`.

Особенности:
  * учитывает заголовки прокси (Cloudflare Tunnel) только от доверенных адресов TRUSTED_PROXY_IPS;
  * пишет PID в data/server.pid и следит за файлом data/stop.flag — так stop.bat корректно
    останавливает сервер (с завершением жизненного цикла приложения), без принудительного убийства процесса.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import uvicorn

from .config import ConfigError, load_settings
from .main import create_app


def pid_alive(pid: int) -> bool:
    """Проверяет, жив ли процесс, не затрагивая его.

    ВАЖНО: на Windows os.kill(pid, 0) не «проверяет», а принудительно завершает процесс,
    поэтому там используется WinAPI.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"\nОШИБКА НАСТРОЕК: {exc}\n", file=sys.stderr)
        return 2

    data_dir = settings.data_path
    data_dir.mkdir(parents=True, exist_ok=True)
    pid_file, stop_flag = data_dir / "server.pid", data_dir / "stop.flag"
    stop_flag.unlink(missing_ok=True)

    if pid_file.exists():
        try:
            old = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            old = 0
        if pid_alive(old) and old != os.getpid():
            print(f"\nОШИБКА: сервер уже запущен (PID {old}). Сначала запустите stop.bat.\n"
                  f"Если вы уверены, что он не запущен, удалите файл {pid_file} и повторите.\n", file=sys.stderr)
            return 3
        pid_file.unlink(missing_ok=True)  # устаревший файл после аварии

    app = create_app(settings)
    config = uvicorn.Config(
        app, host=settings.host, port=settings.port,
        proxy_headers=True, forwarded_allow_ips=settings.trusted_proxy_ips,
        log_config=None, access_log=False, server_header=False, date_header=True,
        timeout_keep_alive=15,
    )
    server = uvicorn.Server(config)

    def watch_stop_flag() -> None:
        while not server.should_exit:
            if stop_flag.exists():
                stop_flag.unlink(missing_ok=True)
                server.should_exit = True
                return
            time.sleep(0.5)

    threading.Thread(target=watch_stop_flag, daemon=True).start()
    pid_file.write_text(str(os.getpid()))
    print(f"SportCourts слушает http://{settings.host}:{settings.port}  (остановка: stop.bat или Ctrl+C)")
    try:
        server.run()
    finally:
        pid_file.unlink(missing_ok=True)
        stop_flag.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
