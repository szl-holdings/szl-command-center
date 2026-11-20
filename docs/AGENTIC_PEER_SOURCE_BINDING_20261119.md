# Agentic peer coding — two-sided source-binding witness

**Scope:** source-only repair of the read-only Command Center release-impact
validator. Kimi K3.1 Pro proposed review constraints through the local Ollama
API; the operator independently reproduced the defect, wrote the patch, and
ran the tests. **Kimi did not execute commands or receive any credentials.**

**Protected source baseline:** `3183f623c4a23e35c5ea233c9a58b14f9b966b0f`,
in `szl-holdings/szl-command-center`.

## Defect and threat model

The release-impact code originally required the release-fabric's
`content_sha256` to match its own serialized graph, but did not independently
recompute `source_snapshot_sha256` from the five collector observations.
An adversarial *in-memory* ontology could alter a collector state and rebuild
the release fabric while retaining an unchanged external snapshot basis.

This does **not** demonstrate an exploitable public HTTP route: the current
API obtains its ontology from a separate controlled projection and the
feature remains disabled unless expressly enabled. The defect is an
internal-consistency gap at a reusable validator boundary.

## Exact source calculus

The source owner `backend/ontology.py` defines:

```text
C(x) = UTF8(JSON(x, sort_keys=True, separators=(",", ":"),
                 ensure_ascii=True, allow_nan=False))
source_basis = SHA256(C({
    "source_generated_at": stamp,
    "observations": [
        [node.id, node.truth_state, node.observed_at,
         node.evidence_ref_sha256] for the five ordered source nodes
    ],
}))
```

`backend/release_impact.py` now checks the exact emitted six-node shape,
the order `github, huggingface, cloudflare, dns, receipts`, bounded and
typed observation fields, and explicitly false action-authority flags.
After the existing static release-stage, edge and fabric-content checks it
recomputes the independent basis above. A changed source observation plus a
rehashed fabric cannot reuse the original basis.

**This proves only internal canonical consistency.** An attacker able to
replace both a source document and its digest can construct a different
internally consistent document. No signer identity, independent collector
attestation, timestamp truth, event completeness, evidence existence,
customer authorization, production release, or paid-provider authority is
established here.

## Independent two-sided evaluation

Using a newly created, disposable checkout of the *exact protected baseline*,
the operator inserted the new synthetic test suite **without changing the
original source implementation**:

- **RED:** 18 tests ran; 12 failed as expected for accepted tampering, stale
  hashes, invalid snapshot fields, wrong-order source IDs and metadata shape.
- A candidate implementation passed 18/18. An additional hostile
  `reason_code=[]` test initially produced `TypeError`; the candidate
  was then corrected to require a string before membership validation.
- **GREEN:** 19/19 then passed, followed by 21/21 after adding a case that
  rejects `action_authorized=0` (rather than boolean `False`) and a
  malformed list-valued `observed_at` field. All source and test files were
  fetched by immutable commit and checked against their Git blob identity.
- Only the disposable checkout was used; no installed Command Center,
  production container, training dispatcher, provider endpoint or source
  branch was modified during local tests.

The test suite includes a separate, explicitly **non-authorizing** positive
case: if an adversary changes all fields, recomputes a new source basis and
fabric, and supplies that *new* basis, the document may still be internally
consistent. Every release-impact output keeps `action_authorized=false`,
`can_deploy=false` and `fingerprint_is_signature=false`.

## Research inputs, first-party implementation

The method combines two-sided blinded grading ideas from
[SWE-bench Pro V2](https://labs.scale.com/leaderboard/swe_bench_pro_public_v2),
the separated workspace/agent/automation boundaries of
[OpenHands](https://github.com/OpenHands/software-agent-sdk), and
the minimal isolated-coding-agent philosophy of
[mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent).
No external source code, model weights or datasets are copied.

The checked code remains a pure Python projection and adds no routes,
network calls, storage writes, new collectors, secrets, permissions,
feature-flag changes or runtime process management.

## Release admission

The source must pass normal CI, including the existing Command Center route
tests, plus independent review. A passing source-level test is not
deployment proof; a separate pinned image/Space and authenticated issuer
evaluation would be required before relying on external claims. Do **not**
translate a checksum into an attestation or grant Kimi shell/secret authority
because the red/green suite passes.
