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
| `GET /api/health` | Liveness                                                                 |

Responses are cached 60s in-memory; the frontend polls every 30s.

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
