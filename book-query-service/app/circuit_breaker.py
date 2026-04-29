"""Same circuit breaker as A3 for recommendation service."""
import time
import threading

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

OPEN_DURATION_SECONDS = 60


class CircuitBreaker:
    def __init__(self):
        self._state = CLOSED
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == OPEN:
                if time.time() - self._opened_at >= OPEN_DURATION_SECONDS:
                    self._state = HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        current = self.state
        return current in (CLOSED, HALF_OPEN)

    def record_success(self):
        with self._lock:
            self._state = CLOSED

    def record_failure(self):
        with self._lock:
            self._state = OPEN
            self._opened_at = time.time()


recommendation_cb = CircuitBreaker()
