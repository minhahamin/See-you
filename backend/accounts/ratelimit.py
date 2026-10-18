"""무차별 대입을 막는 간단한 시도 횟수 제한 (프로세스 메모리, 서비스 인스턴스 1개 기준)."""
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Callable


class AttemptLimiter:
    """키별로 window_sec 동안 max_attempts번까지만 허용한다."""

    def __init__(self, max_attempts: int, window_sec: float, clock: Callable[[], float] = time.monotonic) -> None:
        """한도와 시간 창, 테스트용 시계를 받는다."""
        self._max = max_attempts
        self._window = window_sec
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str) -> deque[float]:
        events = self._events[key]
        cutoff = self._clock() - self._window
        while events and events[0] <= cutoff:
            events.popleft()
        return events

    def retry_after(self, key: str) -> int:
        """한도를 넘었으면 풀릴 때까지 남은 초, 아니면 0."""
        with self._lock:
            events = self._prune(key)
            if len(events) < self._max:
                return 0
            return max(1, int(events[0] + self._window - self._clock()) + 1)

    def hit(self, key: str) -> None:
        """시도 한 번을 기록한다."""
        with self._lock:
            self._prune(key).append(self._clock())

    def reset(self, key: str) -> None:
        """성공하면 기록을 비운다."""
        with self._lock:
            self._events.pop(key, None)
