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
