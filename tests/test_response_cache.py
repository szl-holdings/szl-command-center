"""Offline cache concurrency/failure checks; no provider or framework imports."""
from concurrent.futures import Future, ThreadPoolExecutor
import threading
import unittest
from unittest.mock import Mock, patch

from backend.cache import CacheUnavailable, ResponseCache


class ResponseCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.cache = ResponseCache(60, clock=lambda: self.now)

    def exercise_concurrent(self, producer):
        """Hold the leader until all three followers are actually waiting."""
        owner_entered = threading.Event()
        release = threading.Event()
        followers = threading.Barrier(4)
        calls = []

        class ObservedFuture(Future):
            def result(self, timeout=None):
                followers.wait(timeout=3)
                return super().result(timeout=3)

        def held_producer():
            calls.append(1)
            owner_entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("test producer was not released")
            return producer()

        with patch("backend.cache.Future", ObservedFuture):
            with ThreadPoolExecutor(max_workers=4) as pool:
                owner = pool.submit(self.cache.get, "estate", held_producer)
                try:
                    self.assertTrue(owner_entered.wait(timeout=3))
                    waiting = [pool.submit(self.cache.get, "estate", held_producer) for _ in range(3)]
                    followers.wait(timeout=3)
                finally:
                    release.set()
        return owner, waiting, calls

    def test_four_concurrent_misses_run_one_producer(self):
        payload = {"generated_at": "fixture", "summary": {"estate_state": "UNKNOWN"}}
        owner, followers, calls = self.exercise_concurrent(lambda: payload)
        self.assertEqual(len(calls), 1)
        for result in [owner, *followers]:
            self.assertIs(result.result(timeout=1), payload)

    def test_failed_flight_releases_every_waiter_and_backs_off(self):
        def fail():
            raise ValueError("inert failure")
        owner, followers, calls = self.exercise_concurrent(fail)
        with self.assertRaises(ValueError):
            owner.result(timeout=1)
        for follower in followers:
            with self.assertRaises(CacheUnavailable):
                follower.result(timeout=1)
        self.assertEqual(len(calls), 1)
        retry = Mock(return_value={"truth_state": "UNKNOWN"})
        with self.assertRaises(CacheUnavailable):
            self.cache.get("estate", retry)
        retry.assert_not_called()
        self.now = 60
        self.assertEqual(self.cache.get("estate", retry), {"truth_state": "UNKNOWN"})
        retry.assert_called_once()

    def test_interrupted_owner_releases_waiters_without_swallowing_interrupt(self):
        def interrupt():
            raise KeyboardInterrupt("synthetic interruption, not an OS signal")
        owner, followers, _ = self.exercise_concurrent(interrupt)
        with self.assertRaises(KeyboardInterrupt):
            owner.result(timeout=1)
        for follower in followers:
            with self.assertRaises(CacheUnavailable):
                follower.result(timeout=1)

    def test_ttl_starts_when_successful_collection_finishes(self):
        def slow():
            self.now = 70
            return {"generated_at": "fixture"}
        payload = self.cache.get("estate", slow)
        next_producer = Mock(return_value={"generated_at": "next"})
        for self.now in (70, 129.99):
            self.assertIs(self.cache.get("estate", next_producer), payload)
        next_producer.assert_not_called()
        self.now = 130
        self.assertEqual(self.cache.get("estate", next_producer), {"generated_at": "next"})
        next_producer.assert_called_once()

    def test_failure_backoff_starts_when_collection_finishes(self):
        def slow_failure():
            self.now = 70
            raise ValueError("inert failure")
        with self.assertRaises(ValueError):
            self.cache.get("estate", slow_failure)
        next_producer = Mock(return_value={"truth_state": "UNKNOWN"})
        self.now = 129.99
        with self.assertRaises(CacheUnavailable):
            self.cache.get("estate", next_producer)
        next_producer.assert_not_called()
        self.now = 130
        self.cache.get("estate", next_producer)
        next_producer.assert_called_once()

    def test_failed_refresh_backs_off_without_reusing_expired_entry(self):
        old = {"generated_at": "old", "truth_state": "VERIFIED"}
        self.cache.get("estate", lambda: old)
        self.now = 60
        with self.assertRaises(ValueError):
            self.cache.get("estate", Mock(side_effect=ValueError("inert failure")))
        retry = Mock(return_value={"generated_at": "next"})
        with self.assertRaises(CacheUnavailable):
            self.cache.get("estate", retry)
        retry.assert_not_called()

    def test_different_keys_collect_independently(self):
        entered = threading.Event()
        release = threading.Event()
        def slow():
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("test producer was not released")
            return {"source": "estate"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            estate = pool.submit(self.cache.get, "estate", slow)
            try:
                self.assertTrue(entered.wait(timeout=3))
                verticals = pool.submit(self.cache.get, "verticals", lambda: {"source": "verticals"})
                self.assertEqual(verticals.result(timeout=1), {"source": "verticals"})
            finally:
                release.set()
            self.assertEqual(estate.result(timeout=1), {"source": "estate"})

    def test_unavailable_envelopes_remain_normal_cached_observations(self):
        envelope = {"truth_state": "UNAVAILABLE", "reason": "synthetic missing capability"}
        producer = Mock(return_value=envelope)
        self.assertIs(self.cache.get("estate", producer), envelope)
        self.assertIs(self.cache.get("estate", producer), envelope)
        producer.assert_called_once()

    def test_falsey_payloads_are_still_cached(self):
        for payload in (None, {}, False, 0):
            with self.subTest(payload=payload):
                cache = ResponseCache(60, clock=lambda: self.now)
                producer = Mock(return_value=payload)
                cache.get("estate", producer)
                self.assertIs(cache.get("estate", producer), payload)
                producer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
