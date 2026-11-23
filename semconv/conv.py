"""OpenTelemetry metric semantic-convention registry (propose-only).

Doctrine (leader-study, #26 read-only): metric names follow the OTel
semconv shape: dot-separated lowercase segments, each [a-z][a-z0-9]*,
with underscores permitted ONLY inside the final segment (e.g.
http.server.duration, db.client.operation.duration; http_server.duration
is invalid). Units come from a small declared allowlist; instruments from
the four sync kinds; monotonicity may only be declared on counters.

Sample validation is fail-closed per Kimi W32 amend 4: non-finite floats
(NaN/inf), booleans, and negative values on monotonic counters are all
rejected. Registration rejects same-name conflicts in unit, instrument,
or monotonicity; exact duplicate re-registration is a no-op (amend 3).

Honest limitation, verbatim: structural convention checking only; no
OTLP emission, no network, no attribute-value taxonomy enforcement;
samples are deterministic name + sorted-attrs + value structures.

Propose-only, unsigned; merges are owned by the estate signature wall.
No status claims are made about any other pull request.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict

SCHEMA_VERSION = "szl.semconv/v1"
BANNER = "PROPOSAL_ONLY_UNSIGNED"

UNITS = ("s", "ms", "By", "{request}", "1")
INSTRUMENTS = ("counter", "up_down_counter", "gauge", "histogram")
SEGMENT = re.compile(r"^[a-z][a-z0-9]*$")
FINAL_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")


class SemConvError(ValueError):
    """A metric definition or sample violates the conventions."""


@dataclass
class MetricDef:
    name: str
    unit: str
    instrument: str
    monotonic: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise SemConvError("name must be a non-empty string")
        parts = self.name.split(".")
        if len(parts) < 2:
            raise SemConvError("name needs at least namespace.segment")
        for seg in parts[:-1]:
            if not SEGMENT.match(seg):
                raise SemConvError("segment %r invalid: underscores belong only in the final segment" % (seg,))
        if not FINAL_SEGMENT.match(parts[-1]):
            raise SemConvError("final segment %r invalid" % (parts[-1],))
        if self.unit not in UNITS:
            raise SemConvError("unit must be one of %r" % (UNITS,))
        if self.instrument not in INSTRUMENTS:
            raise SemConvError("instrument must be one of %r" % (INSTRUMENTS,))
        if self.monotonic and self.instrument != "counter":
            raise SemConvError("monotonic may only be declared on counters")


class Registry:
    """Registered metric definitions; conflicting duplicates rejected.

    An exact duplicate (same name, unit, instrument, monotonic) is a
    no-op; same name with ANY changed field (unit, instrument, or
    monotonic) is rejected (Kimi W32 amend 3).
    """

    def __init__(self):
        self._defs: Dict[str, MetricDef] = {}

    def register(self, m: MetricDef):
        if not isinstance(m, MetricDef):
            raise SemConvError("register requires a MetricDef")
        prior = self._defs.get(m.name)
        if prior is not None:
            if (prior.unit != m.unit or prior.instrument != m.instrument
                    or prior.monotonic != m.monotonic):
                raise SemConvError(
                    "duplicate metric %s with different unit/instrument/monotonic rejected" % m.name)
            return  # exact duplicate re-registration is a no-op
        self._defs[m.name] = m

    def definition(self, name: str) -> MetricDef:
        if name not in self._defs:
            raise SemConvError("unknown metric %r; register it first" % (name,))
        return self._defs[name]

    def sample(self, name: str, attrs: dict, value: float) -> Dict[str, object]:
        """Deterministic flat sample: name + sorted attrs + value.

        Fail-closed value validation (Kimi W32 amend 4): non-numeric and
        boolean values are rejected; NaN/inf are rejected; monotonic
        counter samples must be >= 0.
        """
        m = self.definition(name)  # fails closed on unknown names
        if not isinstance(attrs, dict):
            raise SemConvError("attrs must be a dict")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SemConvError("value must be numeric")
        if not math.isfinite(value):
            raise SemConvError("value must be finite (NaN/inf rejected)")
        if m.monotonic and value < 0:
            raise SemConvError("monotonic counter samples must be >= 0")
        return {"schema_version": SCHEMA_VERSION, "banner": BANNER,
                "name": name,
                "attrs": {k: attrs[k] for k in sorted(attrs)},
                "value": value}
