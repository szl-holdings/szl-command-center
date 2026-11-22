# Domain Leader Study — szl-command-center (governed business observability)

OUROBOROS phase-3, cohort-02 tranche-2, Kimi ruling W26-C2T2-KIMI-20261123-ASK (GO, 7 bindings). PROPOSE-ONLY, DRAFT. Documentation only, no implementation in this PR.

## Current state (repo inspection 2026-11-23)
Python repo; description: SZL Command Center governed business observability across the estate. Topics: business-intelligence, estate, governed-ai, observability, python, szl-holdings.

## Domain leaders studied
| Leader | What they have | Key sources |
| --- | --- | --- |
| OpenTelemetry semantic conventions (metrics) | The industry-standard naming + attribute vocabulary for metric signals (counters, up-down counters, gauges, histograms with unit conventions) — the way cross-system dashboards stay comparable instead of bespoke | opentelemetry.io/docs/specs/semconv/general/metrics/ (open-telemetry/semantic-conventions docs/general/metrics.md) (accessed 2026-11-23) |

## What the leader does better
- One shared vocabulary across producers: a panel built on semconv metrics can be compared to any other instrumented system without custom mapping — the observability analog of the estate receipts-schema doctrine.
- Instrument-kind + unit conventions are normative, so aggregation mistakes (sum-where-gauge) are detectable from metadata, not from incident postmortems.

## Gaps
- Description-measured observability exists, but no documented mapping to semconv metric names/units was found in card scope; bespoke estate metric keys cannot be cross-compared outside the estate.

## Ranked #1 absorb proposal (NOT implemented in this PR)
Document the estate-metric → semconv mapping (name, instrument kind, unit) as a sidecar table alongside existing keys, additive and lossless. Expected benefit: command-center panels become comparable with standard OTel tooling; future ingest (e.g. upstream services) maps for free. Cost/risk: low; sidecar only, existing keys unchanged. Validation: mapping covers every currently displayed metric; render unchanged. Rollback: sidecar removal only.

## Sources
- OTel metrics semconv: https://opentelemetry.io/docs/specs/semconv/general/metrics/ (accessed 2026-11-23)
- Spec source: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/general/metrics.md (accessed 2026-11-23)
