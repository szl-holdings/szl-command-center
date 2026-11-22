# SZL Unified Stack — local Python operator control (source-only research preview)

**Owner:** `szl-holdings/szl-command-center`, under the GitHub `szl-holdings` source of truth. **Status: HOLD** for all paid jobs, DNS, deployment, token-store and x402 changes.

## Why this is one control layer, not one machine

The operator view is a bounded catalog: one declarative place for source ownership, independently read provider metadata, and a strictly non-executing job plan. Four compute pools remain separate: SaladCloud GPU, Massed A6000 nodes, Hugging Face Jobs and BETTERWITHAGE **development only**. This avoids binding cluster availability to the laptop. It does **not** provision a Cloudflare Worker or grant permission to submit jobs.

Public design influences were studied for concepts, not copied code: [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/) distinguish desired state from observed state, while [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/) attaches explicit ownership to source-controlled systems. This implementation intentionally contains **no reconciliation actor or mutation loop**. Provider evidence is not conflated with release authority.

The originally described `/workspace/chakana/unified-stack/` files were not mounted on BETTERWITHAGE in this session. This is therefore a source-owned bounded first implementation, not a claim to have implemented Chakana's unseen plan verbatim.

## Python-only frontend and backend

- `backend/unified_ops.py` defines the FastAPI router and renders semantic HTML entirely in **Python** with escaped dynamic values. The frontend has no JavaScript, browser tokens, cookie store or external CDN dependencies.
- `GET /ops/unified`: Basic-authenticated, **localhost-bound** operator view; shows eight source-owned repositories, four compute pools, Hub provider stages, known staging visibility discrepancy, and explicit HOLD admission.
- `GET /api/ops/unified`: same facts in bounded JSON, no-store and noindex. Protected-main and public Hub metadata are queried from **fixed HTTPS origins**; redirects, arbitrary user URLs and overlarge responses are refused. A 60-second single-flight cache bounds rate usage.
- `POST /api/ops/unified/plan` and `POST /ops/unified/plan`: strict four-field declarations (`pool`, `repository`, immutable 40-character `source_sha`, `workload`). They produce a deterministic, non-persisted `HOLD` plan digest; **never** query secrets, allocate compute, append queue records, deploy, sign or settle payments.
- `POST /api/ops/unified/dispatch`: **403 HOLD**. BETTERWITHAGE cannot be selected as a production dispatch pool.
- `backend/main.py` includes the router only in local source checkouts. `backend/source_manifest.py` explicitly excludes `backend/unified_ops.py` from **public Docker/HF images**. The public-image import is independently tested without that module. There is no operator endpoint in the public-derived application.

## Local owner run (no deployments or paid compute)

Run from a **clean** source checkout on BETTERWITHAGE, not an Internet-facing host. Configure a **temporary**, independent password in that PowerShell process:

```powershell
Set-Location C:\SZL\work\szl-command-center-unified-20261120
$cred = Get-Credential -Message 'Enter a disposable LOCAL operator name and strong password'
$env:SZL_UNIFIED_OPS_USER = $cred.UserName
$env:SZL_UNIFIED_OPS_PASSWORD = $cred.GetNetworkCredential().Password
$env:SZL_UNIFIED_OPS_READONLY_ENABLED = '1'
$env:SZL_COMMAND_CENTER_MODE = 'private_ops'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8707
```

Open `http://127.0.0.1:8707/ops/unified` on **that device only**, use the same one-time credentials, then stop the local process. Afterwards clear `SZL_UNIFIED_OPS_USER`, `SZL_UNIFIED_OPS_PASSWORD` and `SZL_UNIFIED_OPS_READONLY_ENABLED` from the shell environment. This uses HTTP Basic **only over loopback**; never use public tunnels, `0.0.0.0`, port forwards or a proxy. The gate requires a loopback client and loopback server socket; forwarded headers fail closed. Public-preview image markers override even valid private credentials.

The operator password is not a Cloudflare service token, org admin credential, GitHub PAT, HF access token, payment key, cluster key or secret-store substitute.

## Verified implementation vs unproved release

On November 20, 2026, a disposable local loopback server returned:

| Check | Evidence | Qualification |
| --- | --- | --- |
| Anonymous operator JSON request | HTTP 401 | Auth boundary observed locally |
| Authenticated operator JSON | HTTP 200; eight GitHub protected-main sources observed | Source metadata only, not code signature |
| Python-rendered operator HTML | HTTP 200; no-store | UI locally exercised, not cloud production |
| Four compute pools | Catalog shown, all UNAVAILABLE | Live provider cost/identity not independently checked |
| Constellation private staging | DRIFT: anonymous Hub says public | Source owner must review visibility; no change made |
| Job plan | HTTP 200, HOLD, no submission | Plan input validation only |
| Dispatch attempt | HTTP 403 | No executor or spend authorized |
| Public Docker bundle | Operator module absent, import succeeds | Offline derived-image isolation, not deployed-image inspection |

Tests: `python -B -m pytest tests -q` passed **248 tests and 352 subtests** on BETTERWITHAGE in the scoped environment. One existing deprecation warning remains. A real local HTTP smoke used a random disposable Basic password, started a loopback-only server, performed the above readbacks and terminated the server. Its redacted evidence lives at `C:\SZL\work\szl-ten-cycle-convergence\local_unified_http_smoke_20261120.json`.

Kimi via the existing Ollama gateway raised a Host-header trust concern. The implementation uses **both** kernel-observed peer and server-bound loopback socket, and negative tests reject remote Host spoofing and a server bound to `0.0.0.0`. Independently prompted local Ministral raised a missing SHA-regex concern; the regex is present in the full source, and invalid/near-miss SHAs are rejected by tests. These conflicting model reviews are not human code review, signed receipts or production admission.

## Remaining provider admission, in source-owner order

1. **Security & registry:** Reconcile private Constellation staging visibility (draft `szl-constellation#56`), extend `szl-asset-registry` only with source-bound full-asset identity, and keep immutable GitHub protected-main revisions authoritative. No unapproved privacy changes.
2. **Cloudflare perimeter:** Independently verify Worker deployed versions, Access deny behavior and service-to-service clients before deciding `mcp`, `api`, `gpu-lung` exceptions. Never turn a paid public endpoint into a free open GPU route. A Cloudflare control layer/secret broker is **not** installed.
3. **Compute & cost:** Obtain working, authorized read-only Salad API access, Massed/HF Jobs service catalogs, actual usage/budget and sole-dispatcher receipts. Training/spend stays HOLD while provider authorization is unknown.
4. **Source and release:** Require independent non-author review, exact-head required CI, commit/signing policy and a separate signed job manifest before changing an executor. Python peer agreement cannot authorize work.
5. **Packaging and settlement:** Do not publish `szl-receipt` from an unidentified PyPI account. Official PyPI provenance is a publication statement, not a runtime signer. x402 HTTP 402 challenges are not verified settlements.

**No remote or paid operation is performed by this feature.** GitHub `main` release workflows, Hugging Face producers, Cloudflare, PyPI, queue state and maintenance windows are unchanged. This PR must remain draft until reviewed and explicitly admitted.
