"""SZL unified operator console: Python backend + Python-rendered frontend.

Source-owned research preview. No provider writes, queues, secrets in output,
worker deployment, paid compute, signing or release authorization.
"""
from __future__ import annotations

import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.client import HTTPException
from hashlib import sha256
from hmac import compare_digest
from html import escape
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request as URLRequest, build_opener

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import public_preview
from .cache import ResponseCache

router = APIRouter()
CACHE = ResponseCache(60)
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ORG = "szl-holdings"
HF_ORG = "SZLHOLDINGS"
MAX_JSON_BYTES = 65536
MAX_POST_BYTES = 4096

# Explicit catalog: names are first-party source declarations, not runtime claims.
SERVICES = (
    ("Command Center", "szl-command-center", None, "operator/control"),
    ("A11oy", "a11oy", "a11oy", "product/inference"),
    ("Killinchu", "killinchu", "killinchu", "product/defense"),
    ("Hatun", "hatun-mcp", None, "product/tools"),
    ("Holo", "holographic-unify", "holographic-unify", "product/visualization"),
    ("Router", "szl-router", None, "infra/routing"),
    ("Compute bridge", "szl-gpu-bridge", None, "infra/compute"),
    ("Constellation", "szl-constellation", "szl-constellation", "infra/atlas"),
)
POOLS = (
    ("salad", "SaladCloud GPU fleet", "GPU executor", "NO_AUTHENTICATED_FLEET_AND_COST_READBACK"),
    ("massed", "Massed dual A6000 nodes", "GPU inference/training", "NO_GOVERNED_CLUSTER_READBACK"),
    ("hf_jobs", "Hugging Face Jobs", "managed CPU/GPU", "NO_AUTHORIZED_JOB_OR_BUDGET_READBACK"),
    ("betterwithage", "BETTERWITHAGE laptop", "development only", "NOT_A_PRODUCTION_POOL"),
)
ALLOWED_REPOS = frozenset(item[1] for item in SERVICES)
ALLOWED_POOLS = frozenset(("salad", "massed", "hf_jobs"))
ALLOWED_WORK = frozenset(("evaluation", "training", "inference", "batch"))
HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex",
           "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _public_get(url: str) -> dict:
    """Only program-generated fixed public GitHub/Hub GETs, no custom URLs."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ("api.github.com", "huggingface.co"):
        raise ValueError("UNAPPROVED_PUBLIC_SOURCE")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("UNAPPROVED_PUBLIC_SOURCE")
    req = URLRequest(url, headers={"Accept": "application/json",
                                  "User-Agent": "szl-unified-operator-source/1"})
    with build_opener(NoRedirect()).open(req, timeout=7) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("UNEXPECTED_RESPONSE")
        raw = response.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    doc = json.loads(raw.decode("utf-8"))
    if type(doc) is not dict:
        raise ValueError("OBJECT_REQUIRED")
    return doc


def source_row(entry: tuple[str, str, str | None, str]) -> dict:
    label, repo, space, role = entry
    url = f"https://api.github.com/repos/{ORG}/{repo}/branches/main"
    row = {"name": label, "kind": role, "owner": ORG, "repository": repo,
           "source_url": f"https://github.com/{ORG}/{repo}",
           "source_sha": None, "source_state": "UNAVAILABLE",
           "source_reason": "SOURCE_NOT_OBSERVED", "source_observed_at": now(),
           "provider_stage": None, "hub_sha": None,
           "runtime_state": "UNAVAILABLE", "runtime_reason": "NO_HUB_SPACE_BOUND",
           "authenticated_render": False, "signed_receipt": False,
           "production_admitted": False}
    try:
        data = _public_get(url)
        commit = data.get("commit")
        sha = commit.get("sha") if type(commit) is dict else None
        if (data.get("name") == "main" and data.get("protected") is True
                and type(sha) is str and SHA40.fullmatch(sha)):
            row.update(source_sha=sha, source_state="OBSERVED",
                       source_reason="PROTECTED_MAIN_METADATA_ONLY")
        else:
            row["source_state"] = "UNKNOWN"
            row["source_reason"] = "PROTECTED_MAIN_IDENTITY_NOT_ESTABLISHED"
    except (ValueError, OSError, HTTPError, URLError, HTTPException, json.JSONDecodeError):
        row["source_reason"] = "GITHUB_PUBLIC_READ_UNAVAILABLE"
    if space:
        row["runtime_reason"] = "PROVIDER_METADATA_NOT_EXECUTION"
        row["hub_url"] = f"https://huggingface.co/spaces/{HF_ORG}/{space}"
        try:
            doc = _public_get(f"https://huggingface.co/api/spaces/{HF_ORG}/{space}")
            if doc.get("id") == f"{HF_ORG}/{space}" and doc.get("private") is False:
                revision = doc.get("sha")
                runtime = doc.get("runtime")
                stage = runtime.get("stage") if type(runtime) is dict else None
                if type(revision) is str and SHA40.fullmatch(revision):
                    row.update(runtime_state="OBSERVED", hub_sha=revision,
                               provider_stage=stage if type(stage) is str else "UNKNOWN")
                else:
                    row["runtime_state"] = "UNKNOWN"
                    row["runtime_reason"] = "HUB_REVISION_UNVERIFIED"
            else:
                row["runtime_state"] = "UNKNOWN"
                row["runtime_reason"] = "HUB_VISIBILITY_OR_IDENTITY_UNVERIFIED"
        except (ValueError, OSError, HTTPError, URLError, HTTPException, json.JSONDecodeError):
            row["runtime_reason"] = "HUB_PUBLIC_READ_UNAVAILABLE"
    return row



def staging_visibility() -> dict:
    """Detect an accidentally public staging Space without an HF token."""
    space_id = "SZLHOLDINGS/szl-constellation-staging"
    row = {"space_id": space_id, "declared_visibility": "private",
           "state": "UNAVAILABLE", "reason": "ANONYMOUS_HUB_READ_UNAVAILABLE",
           "observed_at": now(), "signed": False, "production_admitted": False}
    try:
        doc = _public_get(f"https://huggingface.co/api/spaces/{space_id}")
        if doc.get("id") == space_id and doc.get("private") is False:
            row.update(state="DRIFT", reason="STAGING_DECLARED_PRIVATE_BUT_PUBLIC")
        elif doc.get("id") == space_id and doc.get("private") is True:
            row.update(state="OBSERVED", reason="HUB_PRIVATE_FLAG_ONLY_NOT_ACCESS_DENIAL_PROOF")
        else:
            row.update(state="UNKNOWN", reason="STAGING_HUB_IDENTITY_UNKNOWN")
    except (ValueError, OSError, HTTPError, URLError, HTTPException, json.JSONDecodeError):
        # Preserve the explicit fail-closed default for unreadable public metadata.
        return row
    return row


def collect_snapshot() -> dict:
    """One read-only census; status is a claim about metadata, not execution."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        items = list(pool.map(source_row, SERVICES))
    observed = sum(row["source_state"] == "OBSERVED" for row in items)
    staging = staging_visibility()
    return {
        "schema": "szl.unified-operator-observation/v1",
        "observed_at": now(), "owner": ORG,
        "source_of_truth": f"https://github.com/{ORG}",
        "source_repos_observed": observed,
        "source_repos_total": len(items),
        "staging_visibility": staging,
        "status": "HOLD", "can_dispatch": False,
        "can_deploy": False, "can_publish": False,
        "authenticated_render_verified": False,
        "signed_execution_verified": False,
        "production_admitted": False,
        "services": items,
        "compute_pools": [
            {"id": key, "name": label, "purpose": purpose,
             "availability": "UNAVAILABLE", "reason": reason,
             "job_dispatch": "HOLD", "spend_observed": False}
            for key, label, purpose, reason in POOLS
        ],
        "control_plane": {
            "desired_architecture": "ONE_CONTROL_LAYER_SEPARATE_COMPUTE_POOLS",
            "cloudflare_worker_deployed": "UNVERIFIED",
            "cloudflare_access_and_deny": "UNVERIFIED",
            "x402_settlement": "UNVERIFIED",
            "provider_secret_store": "UNVERIFIED",
            "job_registry": "SOURCE_DECLARATION_ONLY",
            "monitoring": "THIS_READ_ONLY_OBSERVATION",
        },
        "next_gates": [
            "INDEPENDENT_SOURCE_AND_SIGNER_REVIEW",
            "PROVIDER_AUTH_AND_LIVE_DENY_TESTS",
            "BUDGET_OWNER_APPROVAL_AND_NO_PAID_RETRY",
            "PER_SURFACE_DEPLOY_WINDOW_AND_NEGATIVE_TESTS",
            "EXACT_HEAD_RELEASE_AND_POST_DEPLOY_RECEIPTS",
        ],
    }


def _is_local_request(request: Request) -> bool:
    # Host is user-controlled; it is never sufficient proof of local reachability.
    peer = request.client.host if request.client else ""
    host = request.url.hostname or ""
    server = request.scope.get("server")
    bound = server[0] if isinstance(server, (tuple, list)) and server else ""
    return (
        peer in ("127.0.0.1", "::1", "testclient")
        and bound in ("127.0.0.1", "::1", "testserver")
        and host in ("127.0.0.1", "localhost", "testserver", "::1")
        and not any(h in request.headers for h in (
            "x-forwarded-for", "x-forwarded-host", "forwarded", "x-real-ip"
        ))
    )


def _operator_gate(request: Request) -> JSONResponse | None:
    # Immutable public-preview marker outranks explicit private-mode env.
    if public_preview.active():
        return JSONResponse({"status": "UNAVAILABLE",
                             "reason": "PUBLIC_PREVIEW_OPERATOR_SURFACE_DENIED"},
                            status_code=404, headers=HEADERS)
    if os.environ.get("SZL_UNIFIED_OPS_READONLY_ENABLED") != "1":
        return JSONResponse({"status": "UNAVAILABLE",
                             "reason": "OPERATOR_SURFACE_NOT_ADMITTED"},
                            status_code=503, headers=HEADERS)
    if not _is_local_request(request):
        return JSONResponse({"status": "UNAVAILABLE",
                             "reason": "LOCAL_ORIGIN_REQUIRED"},
                            status_code=403, headers=HEADERS)
    user = os.environ.get("SZL_UNIFIED_OPS_USER", "")
    secret = os.environ.get("SZL_UNIFIED_OPS_PASSWORD", "")
    if not user or not secret or len(secret) < 16:
        return JSONResponse({"status": "UNAVAILABLE",
                             "reason": "OPERATOR_CREDENTIAL_NOT_CONFIGURED"},
                            status_code=503, headers=HEADERS)
    header = request.headers.get("authorization", "")
    if len(header) > 700 or not header.startswith("Basic "):
        return _challenge()
    try:
        raw = base64.b64decode(header[6:], validate=True)
        name, password = raw.decode("utf-8").split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return _challenge()
    # This transient equality check is not password storage: compare byte strings
    # directly in constant time rather than applying a fast, unsalted password hash.
    good_user = compare_digest(name.encode("utf-8"), user.encode("utf-8"))
    good_password = compare_digest(password.encode("utf-8"), secret.encode("utf-8"))
    if not good_user or not good_password:
        return _challenge()
    return None


def _challenge() -> JSONResponse:
    return JSONResponse({"status": "UNAVAILABLE", "reason": "OPERATOR_AUTH_REQUIRED"},
                        status_code=401,
                        headers={**HEADERS, "WWW-Authenticate": 'Basic realm="SZL local operator"'})


def _plan(payload: object) -> dict:
    """Validate a dispatch INTENT only. No provider/queue/secret interaction."""
    if type(payload) is not dict or set(payload) != {"pool", "repository", "source_sha", "workload"}:
        raise ValueError("PLAN_SCHEMA_INVALID")
    pool, repo, source, workload = (
        payload["pool"], payload["repository"], payload["source_sha"], payload["workload"]
    )
    if (type(pool) is not str or pool not in ALLOWED_POOLS
        or type(repo) is not str or repo not in ALLOWED_REPOS
        or type(source) is not str or not SHA40.fullmatch(source)
        or type(workload) is not str or workload not in ALLOWED_WORK):
        raise ValueError("PLAN_VALUE_NOT_ADMITTED")
    data = {"pool": pool, "repository": f"{ORG}/{repo}",
            "source_sha": source, "workload": workload}
    basis = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return {"schema": "szl.unified-job-plan/v1",
            "plan_sha256": sha256(basis).hexdigest(),
            "state": "HOLD", "persisted": False,
            "provider_invoked": False, "job_submitted": False,
            "signed": False, "budget_authorized": False,
            "production_admitted": False, "declaration": data,
            "reason": "NO_SIGNER_BUDGET_PROVIDER_LEASE_OR_DEPLOY_WINDOW"}


async def _bounded_body(request: Request) -> bytes:
    parts = []
    total = 0
    async for part in request.stream():
        total += len(part)
        if total > MAX_POST_BYTES:
            raise ValueError("REQUEST_TOO_LARGE")
        parts.append(part)
    return b"".join(parts)


def _plan_error(reason: str) -> JSONResponse:
    return JSONResponse({"status": "UNAVAILABLE", "reason": reason},
                        status_code=400, headers=HEADERS)


CSS = """
:root{color-scheme:dark;font:15px system-ui,Segoe UI,Arial,sans-serif;
background:#0b1220;color:#e7eef8}
*{box-sizing:border-box}body{max-width:1200px;margin:0 auto;padding:28px}
a{color:#7dd3fc;text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:2.2rem;letter-spacing:-.03em;margin:.25rem 0}
h2{font-size:1.2rem;margin:0 0 16px}.eyebrow{font-size:.76rem;
letter-spacing:.19em;text-transform:uppercase;color:#81a9c8}
.lead{font-size:1rem;color:#a9c3d8;max-width:740px}
.hero{padding:24px;background:linear-gradient(125deg,#132a44,#111a2d);
border:1px solid #32506b;border-radius:20px;margin-bottom:24px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.card,section{background:#121e31;border:1px solid #273b55;border-radius:14px;padding:20px}
section{margin:20px 0}dl{display:grid;grid-template-columns:1fr auto;gap:10px}
dt{color:#98adc1}dd{margin:0;font-weight:700}.chip{display:inline-flex;
border:1px solid #46637a;border-radius:100px;padding:4px 10px;
font-size:.72rem;font-weight:700;letter-spacing:.06em}
.hold{color:#fecaca;border-color:#ef4444}.observed{color:#86efac;
border-color:#15803d}.unknown{color:#fde68a;border-color:#a16207}
table{border-collapse:collapse;width:100%;font-size:.84rem;display:block;overflow:auto}
th,td{text-align:left;border-bottom:1px solid #28384c;padding:12px 10px}
th{color:#b1c8de;font-weight:650}td small{color:#9bb3c9}
.mono{font:12px ui-monospace,Consolas,monospace;word-break:break-all}
.note{color:#aac2d7;font-size:.87rem}fieldset{border:0;padding:0}
label{display:block;color:#b4c8df;margin:10px 0 4px}
input,select,button{border:1px solid #3c5575;border-radius:9px;
padding:10px 11px;background:#172943;color:#eff6ff;width:100%}
button{width:auto;background:#0e7490;cursor:pointer;margin-top:15px;
font-weight:700}button:hover{background:#0369a1}.warning{color:#fecaca}
aside{background:#202b3c;border-left:3px solid #f59e0b;padding:14px;margin:15px 0}
footer{margin:28px 0;color:#809cb6}
"""

HTML_HEADERS = {**HEADERS,
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"}


def _chip(value: str) -> str:
    state = "observed" if value == "OBSERVED" else "hold" if value in ("HOLD", "DRIFT") else "unknown"
    return f'<span class="chip {state}">{escape(value)}</span>'


def render(snapshot: dict, plan: dict | None = None) -> str:
    services = []
    for row in snapshot["services"]:
        expected_href = f"https://github.com/{ORG}/{row['repository']}"
        raw_href = (expected_href if row["repository"] in ALLOWED_REPOS
                    and row.get("source_url") == expected_href
                    else f"https://github.com/{ORG}")
        href = escape(raw_href, quote=True)
        sha = row["source_sha"]
        source = _chip(row["source_state"])
        revision = escape(sha[:12]) if sha else "—"
        stage = escape(str(row["provider_stage"] or "NOT VERIFIED"))
        services.append(
            f'<tr><td><strong>{escape(row["name"])}</strong><br>'
            f'<small>{escape(row["kind"])}</small></td>'
            f'<td><a href="{href}" rel="noopener noreferrer">{escape(row["repository"])}</a>'
            f'<br><small class="mono">{revision}</small></td>'
            f'<td>{source}<br><small>{escape(row["source_reason"])}</small></td>'
            f'<td>{_chip(row["runtime_state"])}<br><small>{stage}</small></td>'
            f'<td>{_chip("HOLD")}</td></tr>'
        )
    pools = []
    for pool in snapshot["compute_pools"]:
        pools.append(
            f'<tr><td><strong>{escape(pool["name"])}</strong>'
            f'<br><small>{escape(pool["purpose"])}</small></td>'
            f'<td>{_chip(pool["availability"])}</td>'
            f'<td>{escape(pool["reason"])}</td><td>{_chip("HOLD")}</td></tr>'
        )
    options_repo = "".join(f'<option value="{escape(i[1])}">{escape(i[1])}</option>'
                           for i in SERVICES)
    options_pool = "".join(f'<option value="{escape(i[0])}">{escape(i[1])}</option>'
                           for i in POOLS if i[0] in ALLOWED_POOLS)
    options_kind = "".join(f'<option value="{escape(k)}">{escape(k)}</option>'
                           for k in sorted(ALLOWED_WORK))
    staging = snapshot.get("staging_visibility") or {
        "state": "UNAVAILABLE", "reason": "NO_STAGING_OBSERVATION"}
    outcome = ""
    if plan is not None:
        outcome = (
            '<aside role="status"><strong>Job plan: HOLD — not submitted.</strong>'
            f'<p>Plan digest: <code class="mono">{escape(plan["plan_sha256"])}</code></p>'
            'No queue, secrets, GPUs, deployments or payments were touched.</aside>'
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SZL Unified Control • Operator Research Preview</title>
<style>{CSS}</style></head><body>
<header class="hero"><span class="eyebrow">SZL Holdings / source-governed operations</span>
<h1>Unified control plane <span class="chip hold">HOLD</span></h1>
<p class="lead">One operator view. Four independent compute pools. GitHub is the source;
Hugging Face observations are not deployment certificates. No action is admitted.</p>
<p><a href="/">Main Command Center</a> &nbsp;·&nbsp;
<a href="/api/ops/unified">JSON source readback</a></p></header>
<aside role="status"><strong>Staging privacy: {_chip(staging["state"])}</strong>
{escape(staging["reason"])} — private by source declaration; no policy change authorized.</aside>
<div class="cards">
<div class="card"><p class="eyebrow">Protected source observed</p>
<h2>{snapshot["source_repos_observed"]} / {snapshot["source_repos_total"]}</h2>
<p class="note">Read-only GitHub API; unsigned metadata.</p></div>
<div class="card"><p class="eyebrow">Compute pools</p><h2>4 separate</h2>
<p class="note">Salad · Massed · HF Jobs · development laptop</p></div>
<div class="card"><p class="eyebrow">Release authority</p><h2>0 admitted</h2>
<p class="note">Independent signer, tests and window remain mandatory.</p></div>
</div>
<section aria-labelledby="services"><h2 id="services">First-party source & runtime registry</h2>
<p class="note">Owner: {escape(snapshot["owner"])} · Observed {escape(snapshot["observed_at"])}.
Provider stage does not establish live authenticated rendering.</p>
<table><thead><tr><th>Service</th><th>GitHub protected main</th>
<th>Source state</th><th>Hub provider stage</th><th>Admission</th></tr></thead>
<tbody>{"".join(services)}</tbody></table></section>
<section aria-labelledby="compute"><h2 id="compute">Independent compute pools</h2>
<table><thead><tr><th>Pool</th><th>Real-time access</th><th>Evidence gap</th>
<th>Dispatch</th></tr></thead><tbody>{"".join(pools)}</tbody></table></section>
<section aria-labelledby="intent"><h2 id="intent">Governed job plan — no execution</h2>
<p class="note">Creates a deterministic, non-persisted HOLD response only. Never submits a job.</p>
{outcome}
<form action="/ops/unified/plan" method="post" autocomplete="off">
<fieldset><label for="repo">Source-owned GitHub repository</label>
<select id="repo" name="repository" required>{options_repo}</select>
<label for="sha">Immutable source SHA (40 lowercase hex)</label>
<input id="sha" name="source_sha" pattern="[0-9a-f]{{40}}" minlength="40"
maxlength="40" spellcheck="false" required>
<label for="pool">Compute pool</label>
<select id="pool" name="pool">{options_pool}</select>
<label for="workload">Workload</label>
<select id="workload" name="workload">{options_kind}</select>
<button type="submit">Prepare HOLD-only plan</button></fieldset></form></section>
<section><h2>Admissibility and safeguards</h2><p class="warning">
Signing, deployment window, verified provider identity, budget approval, negative
tests and post-deploy readback are NOT established.</p>
<p class="note">Cloudflare's control layer, Access policies and x402 settlements are
UNVERIFIED. Python frontend and backend are available for local operator
evaluation only; production scheduling, credential vault and payments are not enabled.</p>
</section><footer>Read-only, local authenticated operator research preview.
No browser JavaScript · No secrets in HTML · No writes to cloud providers.</footer>
</body></html>"""


@router.get("/api/ops/unified")
def api_operator_snapshot(request: Request) -> JSONResponse:
    forbidden = _operator_gate(request)
    if forbidden is not None:
        return forbidden
    snapshot = CACHE.get("operator-only:unified", collect_snapshot)
    return JSONResponse(snapshot, headers=HEADERS)


@router.get("/ops/unified")
def operator_frontend(request: Request):
    forbidden = _operator_gate(request)
    if forbidden is not None:
        return forbidden
    snapshot = CACHE.get("operator-only:unified", collect_snapshot)
    return HTMLResponse(render(snapshot), headers=HTML_HEADERS)


@router.post("/api/ops/unified/plan")
async def api_job_plan(request: Request):
    forbidden = _operator_gate(request)
    if forbidden is not None:
        return forbidden
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return _plan_error("CONTENT_TYPE_JSON_REQUIRED")
    try:
        raw = await _bounded_body(request)
        if not raw:
            raise ValueError("PLAN_BODY_REQUIRED")
        def no_duplicates(pairs):
            doc = {}
            for key, value in pairs:
                if key in doc:
                    raise ValueError("DUPLICATE_PLAN_FIELD")
                doc[key] = value
            return doc
        payload = json.loads(raw, object_pairs_hook=no_duplicates,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 ValueError("INVALID_NONFINITE_JSON")))
        plan = _plan(payload)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return _plan_error("INVALID_OR_UNADMITTED_PLAN")
    return JSONResponse(plan, headers=HEADERS)


@router.post("/ops/unified/plan")
async def frontend_job_plan(request: Request):
    forbidden = _operator_gate(request)
    if forbidden is not None:
        return forbidden
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/x-www-form-urlencoded":
        return _plan_error("FORM_CONTENT_TYPE_REQUIRED")
    try:
        raw = await _bounded_body(request)
        fields = parse_qs(raw.decode("utf-8"), strict_parsing=True,
                          keep_blank_values=True, max_num_fields=5)
        if set(fields) != {"pool", "repository", "source_sha", "workload"}:
            raise ValueError("FORM_FIELDS_INVALID")
        if any(len(v) != 1 for v in fields.values()):
            raise ValueError("DUPLICATE_FORM_FIELD")
        plan = _plan({name: rows[0] for name, rows in fields.items()})
    except (ValueError, UnicodeDecodeError):
        return _plan_error("INVALID_OR_UNADMITTED_PLAN")
    snapshot = CACHE.get("operator-only:unified", collect_snapshot)
    return HTMLResponse(render(snapshot, plan), headers=HTML_HEADERS)


@router.post("/api/ops/unified/dispatch")
def denied_dispatch(request: Request) -> JSONResponse:
    forbidden = _operator_gate(request)
    if forbidden is not None:
        return forbidden
    return JSONResponse({"state": "HOLD", "dispatched": False,
                         "reason": "NO_GOVERNED_EXECUTOR_OR_SIGNER"},
                        status_code=403, headers=HEADERS)
