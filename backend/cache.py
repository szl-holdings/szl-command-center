"""Per-process response caching with one producer per key.

Concurrent misses share an in-flight result. Unexpected producer failures are
not observations: they never renew or return expired payloads. A short retry
backoff avoids serial provider storms while keeping failures distinct from
truth-state envelopes returned normally by a collector.
"""
from concurrent.futures import Future
import threading
import time


class CacheUnavailable(RuntimeError):
    """The current collection failed; no fresh response is available."""


class ResponseCache:
    def __init__(self, ttl=60, *, clock=None):
        self.ttl = ttl
        self._clock = clock if clock is not None else time.monotonic
        self._lock = threading.Lock()
        self._entries = {}
        self._flights = {}
        self._retry_after = {}

    def get(self, key, producer):
        with self._lock:
            now = self._clock()
            hit = self._entries.get(key)
            if hit is not None and now < hit["expires_at"]:
                return hit["payload"]
            # An expired observation must not survive as a fallback response.
            self._entries.pop(key, None)
            if now < self._retry_after.get(key, float("-inf")):
                raise CacheUnavailable("collection unavailable; retry after cache backoff")
            flight = self._flights.get(key)
            owner = flight is None
            if owner:
                flight = Future()
                self._flights[key] = flight

        if not owner:
            succeeded, payload = flight.result()
            if not succeeded:
                raise CacheUnavailable("concurrent collection failed")
            return payload

        try:
            payload = producer()
        except BaseException:
            # Release waiters even if the producer is interrupted. Do not retain
            # exception instances/tracebacks or swallow the owner's interruption.
            with self._lock:
                self._retry_after[key] = self._clock() + self.ttl
                self._flights.pop(key)
            flight.set_result((False, None))
            raise

        with self._lock:
            self._entries[key] = {"expires_at": self._clock() + self.ttl, "payload": payload}
            self._retry_after.pop(key, None)
            self._flights.pop(key)
        flight.set_result((True, payload))
        return payload
