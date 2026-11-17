# SZL Evidence Ontology — read-only candidate
Base: szl-command-center@80bf1f134120fc3c7574c9b8b164a3b2310db5fc.
Status: local candidate only, not pushed or deployed, no approval implied.

## Architecture
Existing collectors -> existing 60-second estate cache -> deterministic evidence graph projection -> /api/ontology -> same-origin frontend panel. Five source nodes are emitted even for missing feeds, with observed-in links only. Stale, future, malformed, or missing evidence identifiers cannot be VERIFIED. No actions, no external calls, no plaintext collector values or evidence URLs, no signatures invented. The graph SHA-256 is a checksum, NOT origin authentication or independent attestation.

## Research adaptation
Palantir Foundry Ontology separates objects, links, actions and fine-grained security; we adopt only a read-only object/link projection, never implicit actions: https://www.palantir.com/docs/foundry/ontology/overview
Microsoft GraphRAG local/global/DRIFT modes require qualified indexed data. This is not GraphRAG: https://microsoft.github.io/graphrag/
LangGraph durable workflow/replay still requires idempotence for external effects; future action admission requires operation IDs and owner approval: https://docs.langchain.com/oss/python/langgraph/persistence
NeMo Guardrails separates input, retrieval, dialog, execution, output rails. Our execution rail denies all action paths: https://docs.nvidia.com/nemo/guardrails/latest/about-nemo-guardrails-library/rail-types
OpenTelemetry GenAI semantic conventions flag potential PII in prompts/messages; telemetry exporter and retention are not implemented here: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/

## Mathematical honesty
Canonical Lutar authority source sampled at lutar-lean@5e8a92917d2d4bfeb371a2372f87a4c7660d996d, claims/locked-formulas.v1.json. F4 is backwards-edge Nat DAG acyclicity, not arbitrary graph or BFT. F7 is an in-memory list FIFO property, not exactly-once durable replay. F22 is List.range monotonicity, not deployed log order. F23/Λ unconditional uniqueness is false as stated and remains an open conjecture; it is neither a probability nor authorization. The adapter neither evaluates nor proves those formulas.

## Admission gates
Exact-head ownership/review; hosted tests and browser end-to-end; private evidence authorization (current app estate API exposure needs separate review); immutable source-to-Hub mapping; independent signed receipts; durable telemetry; restore drill; rollback/SLO. Future graph retrieval needs rights-cleared eval datasets, BM25/RRF/bridge ablations, Recall@k, nDCG@k, abstention, p95 and cost. No borrowed benchmark results.

## Local verification — 2026-11-17 UTC

- Repository base matched current origin/main at execution: `80bf1f134120fc3c7574c9b8b164a3b2310db5fc`; zero pre-existing open PRs in the repository.
- 87 Python unit/contract tests initially passed; three further FastAPI TestClient HTTP tests passed.
- Chromium Playwright ran against a disposable localhost uvicorn server with synthetic collectors: five source cards rendered; graph rollup UNKNOWN; source-snapshot mismatch stayed visibly unavailable; feature disabled stayed unavailable; zero page JavaScript errors. `browser-e2e.json` and a screenshot are preserved in the execution evidence directory. This is not a live source-to-Hub deployment or a public authentication acceptance test.
- The new endpoint is **disabled by default**. Exact opt-in variable: `SZL_ONTOLOGY_READONLY_ENABLED=1`; the disabled endpoint returns HTTP 503 with `FEATURE_NOT_ADMITTED` and does not collect. Both responses use `Cache-Control: no-store` and `X-Robots-Tag: noindex`.
- Live browser /api/estate and /api/ontology fetches must return matching `generated_at` / `source_generated_at` or the UI displays `SOURCE_SNAPSHOT_MISMATCH`. A stale or future source timestamp downgrades VERIFIED to UNKNOWN.
- Existing source collectors remain the only observation authority. The frontend panel uses `textContent`; it renders no raw secret-bearing collector values and has no mutating controls.
- All source-ref values in the graph are SHA-256 digests; these are content fingerprints, not evidence of source authenticity. Evidence verification scope is precisely `collector_observation_only`.

## Release requirement

Do not enable this endpoint on public infrastructure until an authenticated access policy, privacy review, explicit owner approval, current-head CI, and a rollback plan have been verified. A staging release should record the exact GitHub head, image digest, collector source identities, browser trace, active access policy, and a durable receipt that can be independently read back. A green PR check alone does not satisfy production or collaborator-owned admission.
