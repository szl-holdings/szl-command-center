# SZL Command Center

<!-- szl:header v1 -->
<!-- Native identity: szl-brand@4309f6fce89179331b0b3ed8c99494e76c5be256; Orbit v2 icon. -->
<p>
  <a href="https://github.com/szl-holdings">
    <img src="https://raw.githubusercontent.com/szl-holdings/szl-brand/4309f6fce89179331b0b3ed8c99494e76c5be256/kit/logos/orbit-v2/suite/szl-icon-32.svg" alt="SZL Holdings — Orbit v2" width="32" height="32" />
  </a>
</p>

**Control before action. Evidence after.**

[Product](https://a-11-oy.com) · [Proof](https://a11oy.net) · [GitHub organization](https://github.com/szl-holdings)
<!-- /szl:header -->

Governed business observability across the SZL estate — New Relic for
consequential AI actions. Every panel carries a truth state
(`VERIFIED` / `UNKNOWN` / `UNAVAILABLE`) and an evidence reference. No
claim without evidence; a collector failure degrades to `UNAVAILABLE`
with the reason, never to a blank (Zero-Bandaid Law).

## Run

```bash
pip install -r requirements.txt
uvicorn backend.main:app --port 8000
```

One command, no docker-compose. Open <http://localhost:8000>.

## Endpoints

| Route             | Purpose                                                                 |
| ----------------- | ----------------------------------------------------------------------- |
| `GET /`           | Mission-control frontend (static, served by FastAPI)                     |
| `GET /api/estate` | One JSON tree: github, huggingface, cloudflare, dns, receipts + summary |
| `GET /api/verticals` | Five verticals, repos, CI health, open-issue counts                  |
| `GET /api/convergence` | Unsigned temporal witness of main→both origins→seven-store preservation→frontier readiness; never release authorization |
| `GET /api/source-manifest` | Read-only local Docker source-byte self-consistency; never signed origin or action authority |
| `GET /api/ontology` | **Disabled by default**: reuses existing estate cache for a read-only five-source ontology and eight-stage/nine-edge release proof graph; no independent qualification or authority |
| `GET /api/release-impact?source=<five-source-name>&basis=<sha256>` | Same disabled-by-default gate/cache; one read-only, bound counterfactual source-loss rehearsal, never provider state or execution authority |
| `GET /api/health` | Liveness                                                                 |
| `GET /inference` | Python-served measured inference showcase card                         |
| `GET /api/inference/snapshot` | Public evidence JSON: health, model exposure, x402 posture |

Responses are cached 60s in-memory; the frontend polls every 30s. The inference
snapshot collector uses its own 30s cache so `/inference` and
`/api/inference/snapshot` share one bounded public probe window.
The `/inference` route is the Python server-rendered showcase; the existing `/` mission-control dashboard remains a separate legacy static bundle.
The frontend uses same-origin API paths on any port or HTTPS reverse proxy.
Preview publishers may replace the `__PORT_8000__` marker with their backend
proxy URL. A failed poll clears the affected panel's previous status and shows
the current error; the other endpoint's successful observation stays visible.

When live GitHub collection is unavailable or uncertain, dated baked evidence
may appear under `_historical_snapshot` in the API response. Current collector
states, failure reasons and timestamps remain authoritative for the dashboard;
historical evidence never replaces them or contributes to its verified count.

Offline route and rendering checks: install `requirements-dev.txt`, then run
`python -m unittest discover -s tests -v` and
`node --test tests/test_snapshot_display.cjs` (Node 20 or newer).

## Local Python unified operator console (source-only)

An additional **Python-rendered frontend and FastAPI backend** now provide a
source-owned, read-only unified view for `szl-holdings`. The operator surface
is **disabled by default**; it is local-only, protected by a disposable Basic
credential and rejects requests received on a non-loopback server socket.
Its 8-source GitHub/Hugging Face catalog and four independent compute-pool
rows never infer deployment, runtime authentication, signer authority,
GPU spend or x402 settlement from public metadata.

- `GET /ops/unified` — Python server-rendered operator dashboard, no JS.
- `GET /api/ops/unified` — same source/pool observations as JSON.
- `POST /ops/unified/plan` and `POST /api/ops/unified/plan` — deterministic
  **HOLD-only**, non-persisted source-pinned job intent; no execution.
- `POST /api/ops/unified/dispatch` — always **403 HOLD**.

The operator module is explicitly **excluded from the public Hugging Face
Docker bundle** by `backend/source_manifest.py`, and public-image isolation
tests prove it cannot be accidentally exposed in the derived app. No public
preview endpoint, model release, provider secret or workflow is changed.
See [local runbook, architecture, security and test evidence](
docs/UNIFIED_STACK_LOCAL_OPERATOR_20261120.md). All real worker
dispatch, authentication/Access onboarding and production admission
remain HOLD behind existing source-owner gates.

## Local Python Lake graph bridge (not a public endpoint)

The **operator-only**, stdlib Python module
[`backend/lake_operator_bridge.py`](backend/lake_operator_bridge.py)
reads the canonical `szl-lake` evidence-graph JSON **only from
127.0.0.1** when explicitly invoked as a local CLI. It validates
source/selected denominators, bounded organ/decision graph shape,
unsigned SHA3-256 graph checksum and explicit false authority flags.
Redirects, unapproved source values, public-preview mode, malformed
payloads and unavailable Lake are refused. It never starts Lake,
runs inference, signs or appends a receipt, or changes Cloudflare/HF.

Example, only after the Lake owner has admitted a local server:
`py -3 -B -m backend.lake_operator_bridge --port 8088`

This is **not** mounted as a FastAPI route and adds no data or private
collectors to the hosted Command Center image. A local checksum
match is not signer authentication, tenant authorization or
production readiness. See [the source, tests, threat model and
research-to-ecosystem contract](docs/LAKE_GRAPH_OPERATOR_BRIDGE.md).
The independent `szl-formulas` EML paper experiment remains
source-only; no new locked formula or publication is inferred.

## Collectors

Every collector returns
`{value, truth_state, verified_at, evidence_ref[, reason]}`.

| Collector | Source | Evidence ref | Degrades to `UNAVAILABLE` when |
| --- | --- | --- | --- |
| `github` | `gh` CLI | `gh run list`, `gh search issues --owner szl-holdings`, `gh api /repos/.../commits/main` | `gh` missing or unauthenticated |
| `huggingface` | `api.huggingface.co` | `/api/spaces?author=szlholdings` (+models, datasets) | no token in env |
| `cloudflare` | `api.cloudflare.com` | `/zones` → `/dnssec`, `/dns_records` (a-11-oy.com, a11oy.net) | no token in env |
| `dns` | system resolver via `dig` | `dig +short DS` / `NS` for both domains | `dig` missing or query fails; unsigned zones report `UNKNOWN` |
| `receipts` | payload 05 + payload 01 | executes `payloads/05-verifier/a11oy_verify.py` against `scratch/self_audit_bundle.json` and reports the verdict run live | bundle/verifier paths absent |

## Environment

Auth is read from the environment at runtime. **Never hardcode a token.**
Set any of these to turn a collector `VERIFIED`:

- GitHub: `GH_TOKEN` (or `gh auth login`)
- Hugging Face: `HF_TOKEN` (also `HUGGING_FACE_HUB_TOKEN`, `HUGGINGFACE_HUB_TOKEN`, `HUGGINGFACE_TOKEN`, `HF_API_TOKEN`)
- Cloudflare: `CLOUDFLARE_API_TOKEN` (also `CF_API_TOKEN`, `CLOUDFLARE_TOKEN`)

Without them, the affected panels render `UNAVAILABLE` with the exact
missing-credential reason. That is the honest state — the page is
correct either way.

## The receipts panel

The latest self-audit verdict is `INCOMPLETE` — missing evidence, never
`PASS` (Law 4, enforced in `a11oy_verify.py`, not in prose). The panel
displays the verdict, the executed verifier checks, and the bundle
facts. That is the demo.

## Layout

```
backend/
  main.py              FastAPI app, routes, 60s cache, static serving
  verticals.py         the five verticals and their repo membership
  collectors/
    base.py            truth-state envelope + roll-up rules
    github.py          gh CLI collectors (CI runs, issue counts, HEAD)
    huggingface.py     HF API org counts (env-gated)
    cloudflare.py      zone DNSSEC + record/proxy counts (env-gated)
    dns.py             dig DS/NS per domain
    receipts.py        live run of the payload-05 reference verifier
frontend/
  index.html           single page, all panels
  styles.css           mission-control-at-night design system (dark-only)
  app.js               fetch → render → poll(30s); skeletons/error/empty states
  favicon.svg          radar-ring mark
```

## Response caching and failure recovery

Responses are cached in memory for 60 seconds **from collection completion**;
the frontend polls every 30 seconds. Concurrent misses for the same endpoint
share one collection per server process. Estate and verticals can collect
independently. Collector truth-state envelopes keep their existing schema and
observation timestamps.

An unexpected producer exception releases all waiting callers and imposes a
60-second retry backoff from failure completion. Expired payloads are neither
returned nor renewed by a failed refresh. Ordinary `UNAVAILABLE`/`UNKNOWN`
collector envelopes remain valid cached observations. Snapshot handling remains
the responsibility of each route. The cache does not add a global
collector deadline or a cross-process limit: requests may wait for the in-flight
collection, and each Uvicorn worker has its own cache.

Offline cache regressions: `python -m unittest discover -s tests -p test_response_cache.py -v`.

Estate on Hugging Face: models, datasets and Spaces are published under the [SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS) org.


## Temporal convergence witness (experimental)

The new mission-control panel uses a separate 60-second cached
`GET /api/convergence` route. It reads protected GitHub `main` **twice**,
bracketing fixed-origin HTTPS GETs of A11oy build-info, state-store status
and frontier readiness. A change of main during this read produces
`MAIN_MOVED` and cannot be mistaken for parity. Both origins must declare
the same exact main revision, and their fenced writer epochs, global lease
sequences and all seven restored store states must agree.

The panel presents a four-axis evidence vector: source declarations,
seven-store preservation, frontier readiness and independently verified
execution authority. Its source match is **declaration-level**, the lease is
an unsigned HTTP observation, and frontier readiness is the service's own
report. Execution authority is always `NOT_EVALUATED`. Even a completely
green observational vector **never** sets `production_qualified` or
`can_deploy`; a separate signed deployment and execution controller must
evaluate the missing authority classes. The SHA-256 in the response is only
a reproducible observation fingerprint, not a signature.

The collector is read-only: no provider writes, cookies, payment, DNS
mutation, key material in responses or browser session. Unlike the
legacy GitHub estate collector, its protected-main reader uses pinned,
bounded Python stdlib HTTPS to the official GitHub branch endpoint and
does not require the `gh` executable in hosted Python environments.
It requires `main` to be identified as protected, rejects redirects,
non-JSON/oversized/duplicate-key replies, and fails closed on 403
or rate limiting. It accepts an optional `GH_TOKEN` (or `GITHUB_TOKEN`)
from the hosting environment for higher API quota; neither the token
nor upstream exception details are emitted to the dashboard. Anonymous
GitHub API reads are rate-limited, and each witness requires two
independent main reads. Set a provider-scoped read-only token or expect
the source axis to become unavailable after quota exhaustion. Its endpoints are compile-time
pinned HTTPS origins, disallow redirects, limit response size, require
JSON, reject duplicate keys and record only selected fields plus
byte hashes. An HTTP 403 challenge, unavailable GitHub, stale head or
malformed evidence degrades to a reason code and never silently inherits
the previously displayed observation.

Offline regression suites include `tests/test_convergence.py`,
`tests/test_convergence_route.py`, and
`tests/test_convergence_display.cjs`.

## Unified release evidence fabric (source-tested, opt-in)

The existing `GET /api/ontology` now projects **one eight-stage,
nine-dependency release chain** over the existing five collector snapshots,
without performing additional provider reads. GitHub, Hugging Face,
Cloudflare/DNS, and receipts remain metadata observations; runtime,
model evaluation, x402 settlement, and PyPI release qualification are
explicitly **not established**. A metadata-green collector is never enough
to claim a model, payment, production deployment, or package is qualified.

The frontend presents these source-bound requirements as a keyboard-friendly
evidence graph, never an autonomous action console. It reuses the existing
`SZL_ONTOLOGY_READONLY_ENABLED=1` admission flag and remains disabled by
default; in public-preview mode, no privileged collector is queried even if
the flag is set. Checksums are not signatures. The browser now recomputes and verifies
the source-observation, release-fabric and outer-ontology SHA-256 digests
before rendering; missing WebCrypto or any mismatch fails closed. These
digests establish same-origin consistency, not independent authenticity.
See the [complete release-fabric contract](docs/RELEASE_FABRIC.md) and
`tests/test_release_fabric.py`.

## Derived Hugging Face Docker preview

The canonical implementation stays in GitHub. A public, read-only preview
may be derived into `SZLHOLDINGS/szl-command-center`, with a pinned
official Python 3.12 OCI base digest, pinned runtime requirements and a
non-root listener on port 7860. The publisher uploads only the selected
tracked application payload and the generated metadata; `.git`, secrets,
test credentials and unrelated local files are not copied.

`scripts/build_command_center_space.py` builds an exact file table with
SHA-256 digests. `/api/source-manifest` independently measures those bytes
inside the running container. This is an **unsigned self-consistency check**,
not a GitHub source signature or proof of publisher identity.

`scripts/publish_command_center_space.py` defaults to read-only preflight.
`--execute` permits one upload only from a clean local `main` with HEAD
equal to the remote `main`, requires HF organization membership, uses
Hub parent-commit concurrency protection, verifies immutable Hub file bytes,
then requires an exact live source-manifest readback. It cannot mark model
quality, production readiness, payment settlement or execution authorization
as established. It does not create a DNS alias or grant secret access.

The CI Docker contract builds the exact generated bundle and exercises the
route inside an isolated container before promotion. Runbook example:

```sh
python scripts/publish_command_center_space.py --receipt ./preflight.json
# Only within an explicitly approved preview publication:
python scripts/publish_command_center_space.py --execute --receipt ./published.json
```

The existing GitHub and Cloudflare panels may remain UNAVAILABLE in public
preview without scoped credentials. Do not add general-purpose private tokens
solely to make public dashboard metrics appear green. A green
`/api/source-manifest` does not override independent production gates.

## Public-preview versus privileged operator evidence

The deployed Docker image is explicitly `SZL_COMMAND_CENTER_MODE=public_preview`
and also contains a source-manifest marker, so an environment override cannot
silently turn its public HTTP endpoints into a privileged operations console.

**Public ontology snapshot identity:** The `/api/estate` and separately
admitted `/api/ontology` routes now share one *public-only* 60-second,
on-demand in-memory snapshot of the five deliberately UNAVAILABLE
collector envelopes. This cache has no access to or key overlap with the
privileged collector cache; it never executes private provider reads.
Both HTTP responses remain `Cache-Control: no-store`. Sharing the exact
`generated_at` snapshot is necessary for the browser's immutable
source-to-graph equality check; separately created timestamps would
otherwise always disagree. Across multiple independent workers or replicas,
unshared snapshots may legitimately mismatch, in which case the browser
still fails closed rather than silently promoting an unrelated response.
No private readiness or release authority is gained.

CI now exercises this exact binding inside the isolated Docker image with
**dummy** provider credentials and the read-only ontology flag enabled.
It requires both the public estate and ontology to carry the *same* snapshot
timestamp while leaving all private collectors UNAVAILABLE. This does not
enable the feature in the hosted Space or relax any required review.
The five legacy estate collectors (GitHub organization, Hugging Face account,
Cloudflare zone, DNS, receipt verifier) and live vertical repository scans
**are not invoked from public-preview HTTP routes**. The resulting
`/api/estate` and `/api/verticals` use explicit `UNAVAILABLE` envelopes
with reason `PUBLIC_PREVIEW_PRIVILEGED_COLLECTOR_NOT_ADMITTED`. Known vertical
repo-name mappings are static source metadata, never a live repo census.
Neither private provider credentials nor cached/historical privately collected
snapshots may populate those public routes. The ontology projection, when
separately admitted, inherits the same public boundary and can grant no action.

`/api/convergence`, `/api/source-manifest` and the public, non-paying
inference snapshot remain independently observable with their existing evidence
limits; no missing operator evidence is promoted. The preview's 0/5
privileged-collector status is an honest **scope boundary**, not five
verified operational services.

A private operator console is a **separate deployment and admission task**:
authenticate the user at the application ingress with an independently verified
identity token and audience, scope short-lived provider credentials, enforce
role-level data visibility, and publish only separately reviewed/redacted
receipts to this public preview. Merely setting `GH_TOKEN`, `HF_TOKEN`,
`CLOUDFLARE_API_TOKEN`, installing `gh` or `dig`, or passing a
self-declared proxy header does **not** authenticate the viewer. No private
console or token-based bypass is activated by this change.

The Docker CI now injects harmless dummy credentials and asserts that the
public endpoints perform no privileged inventory admission or live repo
collection. This boundary remains active even when the Space environment
is changed to a different mode after the image was built.
