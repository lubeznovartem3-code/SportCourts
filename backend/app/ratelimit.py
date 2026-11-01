"""Простой ограничитель частоты в памяти процесса (достаточно для одного сервера и малой нагрузки)."""
from __future__ import annotations

import time
from collections import deque


class SlidingWindowLimiter:
    """Хранит метки времени событий по ключу и считает их в скользящем окне."""

    def __init__(self, max_keys: int = 10_000, clock=time.monotonic) -> None:
        self._events: dict[str, deque[float]] = {}
        self._max_keys = max_keys
        self._clock = clock

    def _prune(self, key: str, window: float) -> deque[float]:
        now = self._clock()
        q = self._events.get(key)
        if q is None:
            q = deque()
            self._events[key] = q
        while q and now - q[0] > window:
            q.popleft()
        return q

    def count(self, key: str, window: float) -> int:
        return len(self._prune(key, window))

    def hit(self, key: str, window: float) -> int:
        """Записывает событие и возвращает число событий в окне (включая новое)."""
        if len(self._events) > self._max_keys:
            self._events.clear()  # защита от бесконтрольного роста памяти
        q = self._prune(key, window)
        q.append(self._clock())
        return len(q)

    def retry_after(self, key: str, window: float) -> int:
        """Через сколько секунд освободится место в окне (0, если событий нет)."""
        q = self._prune(key, window)
        if not q:
            return 0
        return max(1, int(window - (self._clock() - q[0])) + 1)

    def reset(self, key: str) -> None:
        self._events.pop(key, None)
