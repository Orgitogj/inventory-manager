import math
import threading
import time
from collections import deque
from collections.abc import Callable, Hashable


class LoginRateLimiter:
    def __init__(
        self,
        max_attempts: int,
        max_attempts_per_ip: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._max_attempts_per_ip = max_attempts_per_ip
        self._window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[Hashable, deque[float]] = {}
        self._next_sweep = clock() + window_seconds

    def retry_after(self, ip: str, email: str) -> int | None:
        with self._lock:
            now = self._clock()
            waits = [
                self._wait(key, limit, now) for key, limit in self._limits(ip, email)
            ]

        blocked = [wait for wait in waits if wait is not None]
        return max(blocked) if blocked else None

    def record_failure(self, ip: str, email: str) -> None:
        with self._lock:
            now = self._clock()
            self._sweep(now)

            for key, _limit in self._limits(ip, email):
                self._failures.setdefault(key, deque()).append(now)

    def reset(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.pop((ip, email), None)

    def _limits(self, ip: str, email: str) -> tuple[tuple[Hashable, int], ...]:
        return (
            ((ip, email), self._max_attempts),
            (ip, self._max_attempts_per_ip),
        )

    def _wait(self, key: Hashable, limit: int, now: float) -> int | None:
        failures = self._prune(key, now)

        if len(failures) < limit:
            return None

        expires_at = failures[len(failures) - limit] + self._window_seconds
        return max(1, math.ceil(expires_at - now))

    def _prune(self, key: Hashable, now: float) -> deque[float] | tuple[()]:
        failures = self._failures.get(key)

        if failures is None:
            return ()

        while failures and failures[0] <= now - self._window_seconds:
            failures.popleft()

        if not failures:
            del self._failures[key]

        return failures

    def _sweep(self, now: float) -> None:
        if now < self._next_sweep:
            return

        for key in list(self._failures):
            self._prune(key, now)

        self._next_sweep = now + self._window_seconds
