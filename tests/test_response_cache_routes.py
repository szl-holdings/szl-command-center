"""Exercise both actual route functions with the response cache wired in."""
from concurrent.futures import Future, ThreadPoolExecutor
import json
import threading
import unittest
from unittest.mock import Mock, patch

from backend import main
from backend.cache import CacheUnavailable, ResponseCache


class ResponseCacheRouteTests(unittest.TestCase):
    def routes(self):
        return (
            (main.api_estate, main, "_estate", {"collectors": {}, "generated_at": "live"}),
            (main.api_verticals, main.verticals_mod, "collect", {"verticals": [], "generated_at": "live"}),
        )

    def test_concurrent_route_requests_share_collection(self):
        for route, target, attribute, payload in self.routes():
            with self.subTest(route=route.__name__):
                entered = threading.Event()
                release = threading.Event()
                followers = threading.Barrier(4)

                class ObservedFuture(Future):
                    def result(self, timeout=None):
                        followers.wait(timeout=3)
                        return super().result(timeout=3)

                def produce():
                    entered.set()
                    if not release.wait(timeout=5):
                        raise AssertionError("test collection was not released")
                    return payload

                producer = Mock(side_effect=produce)
                with patch.object(main, "_response_cache", ResponseCache()), patch.object(
                    main, "_snapshot", return_value=None
                ), patch.object(target, attribute, producer), patch("backend.cache.Future", ObservedFuture):
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        owner = pool.submit(route)
                        try:
                            self.assertTrue(entered.wait(timeout=3))
                            waiting = [pool.submit(route) for _ in range(3)]
                            followers.wait(timeout=3)
                        finally:
                            release.set()
                    for result in [owner, *waiting]:
                        response = result.result(timeout=1)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(json.loads(response.body), payload)
                producer.assert_called_once()

    def test_failed_route_refresh_cannot_reuse_expired_payload_or_snapshot(self):
        for route, target, attribute, payload in self.routes():
            with self.subTest(route=route.__name__):
                now = [0.0]
                cache = ResponseCache(60, clock=lambda: now[0])
                producer = Mock(side_effect=[payload, ValueError("offline failure")])
                with patch.object(main, "_response_cache", cache), patch.object(
                    main, "_snapshot", return_value=None
                ) as snapshot, patch.object(target, attribute, producer):
                    self.assertEqual(json.loads(route().body), payload)
                    snapshot.reset_mock()
                    now[0] = 60
                    with self.assertRaises(ValueError):
                        route()
                    with self.assertRaises(CacheUnavailable):
                        route()
                    self.assertEqual(producer.call_count, 2)
                    snapshot.assert_not_called()

    def test_route_ttl_starts_after_slow_collection_finishes(self):
        for route, target, attribute, payload in self.routes():
            with self.subTest(route=route.__name__):
                now = [0.0]
                cache = ResponseCache(60, clock=lambda: now[0])

                def produce():
                    now[0] = 70
                    return payload

                producer = Mock(side_effect=produce)
                with patch.object(main, "_response_cache", cache), patch.object(
                    main, "_snapshot", return_value=None
                ), patch.object(target, attribute, producer):
                    self.assertEqual(json.loads(route().body), payload)
                    now[0] = 129.99
                    self.assertEqual(json.loads(route().body), payload)
                    producer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
