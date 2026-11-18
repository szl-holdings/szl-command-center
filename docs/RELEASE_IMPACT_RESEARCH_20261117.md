# Counterfactual release dependency-loss rehearsal — 2026-11-17

**Status:** source candidate · read-only · disabled unless the pre-existing ontology
feature is explicitly admitted · **not deployed, signed or production qualified**.

## Concrete problem

SZL's existing Command Center already projects five governed collector states
into eight release stages and nine *required but unproven* bindings
(`backend/release_fabric.py`). The existing release fabric never promotes a
collector's VERIFIED metadata to artifact integrity, runtime qualification,
theorem correctness or paid settlement. The new question is narrower:

> If a particular evidence source becomes unavailable, which collector-stage
> observations would actually change, and which downstream release obligations
> are only structurally exposed?

The distinction is central. An upstream failing observation **does not prove
that a machine failed, an API request failed, an operator lost authorization,
or a payment was reversed**. Edges are required obligations, not observed
causal relations.

## Leaders studied and implementation choices

| Reference | Source-backed pattern | Existing SZL adaptation |
|---|---|---|
| [Palantir Foundry Ontology](https://www.palantir.com/docs/foundry/object-backend/overview) and [Actions API](https://www.palantir.com/docs/foundry/api/ontologies-v2-resources/actions/apply-action) | Typed objects, links and separately authorized changes. HTTP 200 alone does **not** mean a requested action was applied successfully. | Keep `source`, `release_stage` and `required_binding` distinct. Every action flag stays false; no operator button can authorize a release. |
| [NVIDIA NeMo 1.9 migration](https://docs.nvidia.com/nemo/agent-toolkit/1.9/resources/migration-guide.html) and [Relay](https://docs.nvidia.com/nemo/relay/getting-started/quick-start) | Relay is for observation/middleware, Fabric for execution, Helix for evaluation. NeMo Agent Toolkit has an October 2026 deprecation and year-end EOL. | This code is **observation only**. Existing SZL Nemo/Hatun/A11oy controllers retain action authority. No deprecated SDK or additional observability exporter is installed. |
| [LangGraph interruption and persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Persisted state and resumable execution require explicit task ownership and safe idempotence for side effects. | Do **not** create another checkpointer, scheduling loop, tool writer or retry authority for this one-shot read-only simulation. |
| [Lean proof validation](https://lean-lang.org/doc/reference/latest/ValidatingProofs/) | The kernel checks formal proof terms; a correct proof does not guarantee a statement's intended informal meaning or runtime refinement. | The strict topological traversal is **F4-motivated**, not a Lean proof of this Python code or of deployed flows. F4 remains the backward-edge Nat DAG fragment, not BFT or causality. |

## Operational contract

The existing `GET /api/ontology` still provides a checksum-checked
source-bound graph. The new **on-demand only** request is

```http
GET /api/release-impact?source=github&basis=<64-lowercase-source-snapshot-sha256>
```

Allowed `source` values are exactly `github`, `huggingface`,
`cloudflare`, `dns`, `receipts`. The server compares `basis` with the
freshly reconstructed current snapshot from the **same existing estate
cache**; an exact mismatch yields HTTP **409** and no graph data. Invalid
values produce **400 before collecting**. Disabled/unadmitted routes produce
**503 FEATURE_NOT_ADMITTED without collector work**.

The output is `szl.readonly.release_impact.v1` and binds the same exact
source and release-fabric digests as the already-checked ontology. It contains
only typed source/stage names and deterministic state transitions. It reports:

1. `collector_stage_changes`: differences in admitted metadata truth when
   just the selected source is hypothetically UNAVAILABLE.
2. `structurally_exposed_stages`: a bounded static DAG transitive closure of
   stage prerequisites, even if there was no new observed metadata loss.
3. `structurally_exposed_edges`: fixed **unproven** release obligations, never
   causal or attestational evidence.
4. `content_sha256`: an unsigned byte-consistency digest, never an
   attestation, signed authority, settlement or independent witness.

The frontend's user-operated control is appended inside the existing release
panel. It causes **zero additional polls**. Before displaying a result it
validates the schema, source and checksum bindings, rechecks the unsigned
SHA-256 in WebCrypto and requires all authority, deployment, model-quality
and revenue flags to remain false. It drops late results from older polls.
Failure is visibly UNAVAILABLE; there is no cached successful fallback. The
feature retains the existing `SZL_ONTOLOGY_READONLY_ENABLED=1` admission
boundary, no new provider credential and no new independent collector.

## Tests and mathematical honesty

- Every one of **3^5 = 243** three-state collector combinations times **five**
  source-withdrawal choices (**1,215 simulations**) keeps
  `production_qualified`, `can_deploy`, `action_authorized`,
  `model_quality_verified`, and `settlement_verified` false.
- An already unavailable source causes no **new** metadata downgrade, but
  remains a structurally relevant prerequisite. Mixed Cloudflare/DNS
  metadata downgrades to UNKNOWN, never to a fictional production failure.
- A backward/cyclic release edge fails closed. The graph is not a causal
  inference system.
- Tests reject tampered stage authorization, false successful edges,
  changed/reordered hashes, unknown source identifiers, and mismatched
  snapshot bases.
- A Python-generated synthetic golden wire receipt is recomputed by the
  actual JavaScript browser-contract test; tampered, wrong-basis or denied
  API results do not render an apparent green badge.
- Public-preview routing uses only the already isolated public synthetic
  cache. Private collector `value` contents, prompts, tokens and payment
  signatures never enter the projection.

## Failure-experiment research lane

Use **held-out** source-withdrawal episodes and actual incident ground truth
to compare a source-only dashboard, the current fixed DAG rehearsal, and a
later approved signed-edge evidence layer. Measure:

- decision-support withdrawal precision/recall with explicit denominators;
- false abstentions and stale-success leaks;
- time-to-diagnosis and false cascade labels;
- exact source/revision evidence, p50/p95 display latency, observer API
  requests and incremental cost;
- independent verifier outcomes, not merely UI green states.

No experiments against live paid inference, new GPU runs, source licensing or
private customer data are authorized by this work. The current patch is a
rehearsal engine, **not** a novel mathematical theorem, completed experiment,
model-quality improvement or production release.

## Acceptance before a hosted release

Source owner reconciliation, signature/checks and existing required PR review;
CI Python/Node tests and source manifest closure; separate decision to enable
`SZL_ONTOLOGY_READONLY_ENABLED` with privacy/access review and rollback;
exact deployed Git SHA/digest; browser readback; then any independently signed
provider bindings through the canonical owners. The endpoint must not replace
A11oy's execution handoff, HF publisher, Cloudflare owner, x402 facilitator,
PyPI Trusted Publisher, or the Flagship54 guard.
