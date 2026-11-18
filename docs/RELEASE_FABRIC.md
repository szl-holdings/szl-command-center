# SZL Command Center — unified release evidence fabric

**Status: SOURCE-TESTED / READ-ONLY / DISABLED BY DEFAULT.**
This is a projection in the existing Command Center, **not** another deployment,
control plane, polling service, wallet, registry writer, payment controller,
model trainer, source verifier, or production admission authority.

## Why consolidate?

The company already has a repository census, Hugging Face collectors, public
runtime witnesses, receipt-verification tooling, and Cloudflare/PyPI release
contracts. They do **not** all attest the same thing. A green GitHub job may
only mean its tests passed, a Space RUNNING state is transport metadata, a
Cloudflare HTTP 402 challenge is not payment settlement, and a PyPI JSON
version is not a byte-and-provenance verified distribution.

The evidence fabric brings **those unproven handoffs onto a single graph**
without manufacturing missing facts. It reuses the Command Center's existing
`/api/ontology` response, its existing 60-second estate cache, and the
existing frontend. **No additional live provider request is made by the
fabric.** There is no new browser origin, scheduler, observer, credential, or
background agent.

## Exact typed graph

`backend/ontology.py` already redacts its estate input into five
`source:<collector>` nodes (github, huggingface, cloudflare, dns, receipts).
For the release overlay, `backend/release_fabric.py` consumes **only** those
already normalized states, their source-snapshot SHA-256, and a finite static
dependency topology. It never reads nested values, bearer tokens, raw
evidence URLs, training data, wallet identifiers, invoice amounts, or payer
records.

Eight release stages are explicitly distinguished:

| Stage | Existing metadata observation | Proof still required |
| --- | --- | --- |
| GitHub source | github collector | Immutable main SHA, checks, reviews |
| Hugging Face catalog | huggingface collector | Pinned model/data bytes and rights |
| Cloudflare / DNS | cloudflare **and** dns collector | Exact rule/method readback and release binding |
| Receipt index | receipts collector | Independent signer and receipt authority |
| Model evaluation | **No admitted collector** | Exact weight binding, denominators, baseline, benchmark version |
| Runtime deployment | **No admitted collector** | Runtime/source identity and authenticated acceptance tests |
| x402 settlement | **No admitted collector** | Facilitator/chain, refund and merchant payout reconciliation |
| PyPI release | **No admitted collector** | Wheel/sdist bytes, PEP 740, source/tag match |

There are nine directional *required* relationships. An edge means
`REQUIRES_*_BINDING`; it is **not** a measured relationship or a verified
lineage claim. Each edge remains `NOT_ESTABLISHED` regardless of the
input collector states. Each stage's `qualification` remains
`NOT_ESTABLISHED`. In v1, all eight independent stage qualifications
remain zero, and no graph output grants action, deployment or revenue
authority.

The pure projection emits:
- `szl.readonly.release_fabric.v1`;
- `basis_source_snapshot_sha256` (exact source-ontology checksum);
- stage and edge records, a deterministic `content_sha256`;
- `collector_verified_stages` (metadata coverage **only**);
- `independently_qualified_stages: 0`;
- `production_qualified: false`, `can_deploy: false`,
  `financial_revenue_verified: false`;
- `fingerprint_is_signature: false`.

**SHA-256 is not a signature.** The reported coverage states can be
`VERIFIED`, `UNKNOWN` or `UNAVAILABLE` only at the collector's original
scope. Missing or stale metadata degrades, never silently adopts a
historical successful observation.

## UI, deployment and security

The frontend adds an accessible, responsive dependency lattice inside its
**existing evidence ontology panel**: eight gate cards and nine missing
provenance links. It uses first-party HTML/CSS/JS and `textContent`, not
`innerHTML`, untrusted URL navigation, WebGL tracking, external graph
libraries, or network mutations. Validation rejects any fabricated
`production_qualified`, `can_deploy`, financial-success or edge-success
claims before rendering.

**New: browser-side SHA-256 recomputation.** Previously, the UI checked
that the three 64-character checksums looked like SHA-256 but did not
recompute them. On every admitted ontology response, native secure-context
WebCrypto now recomputes and compares all three **Python-canonical JSON**
digests: (1) the redacted collector observation snapshot, (2) the
eight-stage release-fabric body, and (3) the complete outer ontology body.
The browser refuses to render a graph if any digest changes, the payload is
oversized/malformed, or SubtleCrypto is unavailable. It does not requery
providers or introduce an external hash library. A Python-generated golden
fixture pins the cross-language serialization contract.

These are **consistency checks of bytes supplied by the same origin**;
an attacker with the ability to replace those bytes and all matching digests
could still fabricate a coherent graph. Provider signatures, trusted GitHub
revision and verified attestation are *independent* missing gates. SHA-256
does not grant action authority or certify payment settlement.

`GET /api/ontology` remains **503 FEATURE_NOT_ADMITTED** until the
existing explicit `SZL_ONTOLOGY_READONLY_ENABLED=1` admission is applied
through its authorized deployment path. **This source change does not set
that flag or deploy the Space.**

In a source-marked public-preview image, the same route—even when
explicitly enabled—must take the dedicated, public-only on-demand
`public_preview.estate()` cache: five UNAVAILABLE metadata collectors and
zero private API calls. The existing `GET /api/estate` uses the same
60-second in-memory **public-only** snapshot, so `source_generated_at`
agrees exactly between graph and estate. It does not reuse a privileged
cache key or historical data and sends `Cache-Control: no-store`.
Independent worker or replica clocks may produce distinct snapshots;
the frontend must reject such mismatches rather than infer alignment.
The isolated Docker CI includes an explicit enabled-feature test using dummy
provider tokens; source and ontology must share the same public snapshot.
No actual environment credential, account setting or Hosted Space variable
is modified by that test. It never substitutes
privileged operator observations from environment variables, cached internal
records, or baked historical snapshots. The new fabric does not change
`/api/health`, public-preview ingress, source manifests, or the original
`/api/estate` and `/api/verticals` response contracts.

## Reproduce without live credentials

```sh
python -m unittest discover -s tests -v
node --test tests/test_snapshot_display.cjs tests/test_convergence_display.cjs
node --check frontend/app.js
```

The release-graph unit tests enumerate all `3^5 = 243` possible collector
truth-state combinations; no combination qualifies a stage, authorizes a
deployment or asserts financial revenue. Route tests confirm a disabled
feature performs no collector work, and public preview cannot access private
collectors. Browser-DOM contract tests reject tampering, prove a historical
green status is not inherited, and exercise the user-visible graph. The updated frontend contract additionally
checks an exact Python-generated golden response, rejects tampering separately
at source, fabric and outer-body checksums, and requires that missing browser
WebCrypto fails closed. The application still does not claim a cryptographic
signature or verified external origin.

## Required next gates

Before promoting the fabric to a verified production evidence graph, an
authorized independent owner must define and sign a versioned source
admission contract, prove exact GitHub/HF deployed source and artifact
identity, bind current weights to repeatable evaluations, verify Cloudflare
rule/method and real x402 settlement with refunds, and check PyPI
distribution files and provenance. Only an independently reviewed future
schema may update edge qualification. **Never modify this v1 module simply
to make a dashboard green.**

There is no background writer, monitor, or paid operation in this change.
