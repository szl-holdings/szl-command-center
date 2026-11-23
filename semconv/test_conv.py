import math
import unittest

from semconv.conv import MetricDef, Registry, SemConvError


def d(name="http.server.duration", unit="s", inst="histogram", mono=False):
    return MetricDef(name=name, unit=unit, instrument=inst, monotonic=mono)


class NameTests(unittest.TestCase):
    def test_valid_names(self):
        for ok in ("http.server.duration", "db.client.operation.duration",
                   "system.cpu.time", "messaging.delivery.count"):
            MetricDef(name=ok, unit="s", instrument="counter")

    def test_underscore_outside_final_segment_rejected(self):
        with self.assertRaises(SemConvError):
            d(name="http_server.duration")
        with self.assertRaises(SemConvError):
            d(name="my.metric_2.duration")

    def test_uppercase_name_rejected(self):
        with self.assertRaises(SemConvError):
            d(name="Http.Server.Duration")
        with self.assertRaises(SemConvError):
            d(name="http.server.DURATION")

    def test_single_segment_rejected(self):
        with self.assertRaises(SemConvError):
            d(name="duration")


class DefTests(unittest.TestCase):
    def test_unknown_unit_rejected(self):
        with self.assertRaises(SemConvError):
            d(unit="seconds")

    def test_unknown_instrument_rejected(self):
        with self.assertRaises(SemConvError):
            d(inst="summation")

    def test_monotonic_on_non_counter_rejected(self):
        with self.assertRaises(SemConvError):
            d(inst="gauge", mono=True)
        with self.assertRaises(SemConvError):
            d(inst="histogram", mono=True)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.r = Registry()

    def test_register_and_sample(self):
        self.r.register(d())
        s = self.r.sample("http.server.duration", {"b": 2, "a": 1}, 0.25)
        self.assertEqual(list(s["attrs"].keys()), ["a", "b"])  # sorted, deterministic
        self.assertEqual(s["value"], 0.25)

    def test_duplicate_conflicting_def_rejected(self):
        # Kimi W32 amend 3: conflicts in unit OR instrument OR monotonic all reject.
        self.r.register(d())
        with self.assertRaises(SemConvError):
            self.r.register(MetricDef(name="http.server.duration", unit="ms", instrument="histogram"))
        with self.assertRaises(SemConvError):
            self.r.register(MetricDef(name="http.server.duration", unit="s", instrument="gauge"))
        with self.assertRaises(SemConvError):
            self.r.register(MetricDef(name="http.server.duration", unit="s",
                                       instrument="histogram", monotonic=True))
        # exact duplicate (all four fields equal) remains a no-op
        self.r.register(d())

    def test_exact_duplicate_registration_is_noop(self):
        self.r.register(d())
        self.r.register(d())
        self.assertIs(self.r.definition("http.server.duration"), self.r._defs["http.server.duration"])

    def test_unknown_metric_sample_rejected(self):
        with self.assertRaises(SemConvError):
            self.r.sample("not.registered", {}, 1)

    def test_non_finite_sample_rejected(self):
        # Kimi W32 amend 4: NaN/inf/bool rejected.
        self.r.register(d())
        for bad in (float("nan"), float("inf"), float("-inf"), True, "x", None):
            with self.assertRaises(SemConvError):
                self.r.sample("http.server.duration", {}, bad)

    def test_negative_monotonic_counter_sample_rejected(self):
        # Kimi W32 amend 4: monotonic counters must be >= 0.
        self.r.register(MetricDef(name="messaging.delivery.count", unit="{request}",
                                  instrument="counter", monotonic=True))
        self.r.sample("messaging.delivery.count", {}, 0)   # zero ok
        self.r.sample("messaging.delivery.count", {}, 5)   # positive ok
        with self.assertRaises(SemConvError):
            self.r.sample("messaging.delivery.count", {}, -1)
        # non-monotonic instruments are not sign-restricted
        self.r.register(d())
        self.r.sample("http.server.duration", {}, -0.5)

    def test_malformed_attrs_rejected(self):
        self.r.register(d())
        with self.assertRaises(SemConvError):
            self.r.sample("http.server.duration", "not-a-dict", 1)


if __name__ == "__main__":
    unittest.main()
