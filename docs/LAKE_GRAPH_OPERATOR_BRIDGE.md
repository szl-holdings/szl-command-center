# SZL Command Center — local Lake graph operator bridge

**Stage:** source-only developer/operator bridge, **not deployed**, **not a public
route**, not a receipt signer, not a tenant authorization or training gate.
Source owner for the graph remains
[`szl-holdings/szl-lake`](https://github.com/szl-holdings/szl-lake).

## Ownership and architecture

```text
SZL Lake validated durable NDJSON
  -> owner-controlled fixed-query SQLite summary
  -> owner-controlled szl.lake.evidence-graph/v1 JSON
  -> explicitly invoked Python operator CLI on localhost
  -> bounded checksum and denominator revalidation
  -> local status report only; NO exposed Command Center API
```

This is **not** a second database or a duplicate graph computation.
The bridge is pure Python stdlib and requires no Cloudflare, Hugging Face,
PyPI, Neon, browser, GPU or infrastructure changes.

## Execution

The Lake server must have been independently admitted and run by its owner,
with `SZL_LAKE_GRAPH_READONLY=1` **in a local, operator-controlled
environment only**. That exact flag does not authenticate any external client.

From a reviewed local Command Center source tree:

```powershell
py -3 -B -m backend.lake_operator_bridge --port 8088
```

The CLI performs an **unauthenticated, redirect-refusing GET only to
127.0.0.1** on the fixed Lake graph path, with a 5-second deadline,
1 MiB response bound, no proxies, cookies, credentials or arbitrary URL.
Optional `--organ` is restricted to the same filesystem-safe organ
identifier grammar used by Lake. It never starts Lake or changes its
flag, service, ledger, training process or checkpoints.

Default public-preview mode, including any image with the pinned
`source_manifest.json`, is **REFUSED before any request**.
There is **no** new `/api/lake-graph` route in Command Center;
ordinary `/api/estate` and `/api/ontology` remain unchanged.

## Validation contract

The bridge checks the exact `szl.lake.evidence-graph/v1` schema,
no-store response, source and selected receipt denominators, normalized
organ IDs, local SHA3-256 chain-head shapes, organ-to-decision counts,
node/edge syntax, empty-ledger state, disabled effects and the checksum:

```text
SHA3-256(canonical_JSON({
  nodes, edges, distributions, source_heads,
  total_source_receipts, selected_receipts, organ_filter
}))
```

It **recomputes the checksum**, but does not authenticate the server or
prove chain non-equivocation. It returns `LOCAL_CHECKSUM_CONSISTENT`
or `EMPTY_UNOBSERVED` with source totals, graph counts and false
authority flags; failures use stable `HOLD` reason codes. It never
prints incoming raw receipt bodies, passwords or arbitrary exception text.

An attacker who can replace a graph and recompute its checksum can still
forge this local consistency report. A production integration needs
separately verified issuer signatures, tenant Access policy, source
identity and immutable deployment readbacks.

## EML paper and formula ecosystem

The new research module
[`szl_formulas.eml_research`](https://github.com/szl-holdings/szl-formulas/tree/main/torch-ext/szl_formulas)
is owned exclusively by `szl-formulas`, not copied into Command Center
or an extra canonical formula slot. Its bounded real-domain numerical
witness credits Odrzywołek's
[arXiv:2603.21852v2](https://arxiv.org/html/2603.21852v2) and reports
explicit complex-branch, proof and training limitations.

A later **operator-authorized** evidence writer may bind a signed EML
test-result receipt to this Lake graph. The current bridge does not
mint or append any receipt and does not turn a numerical identity
test into a new Lean theorem or an inference/model-quality claim.

## Verification and release gates

Run `py -3 -B -m pytest tests/test_lake_operator_bridge.py -q`
against synthetic fixtures. Additional cross-repository smoke should
call Lake's `ReceiptLedger`, `szl_lake_sql.summarize`, and
`szl_lake_graph.project` against a disposable synthetic ledger,
then validate that exact result with this bridge.
The provider, tenant, browser, signing and end-to-end production
integration remain unverified until an authorized staging readback.

No code from Palantir, Anduril, NVIDIA or the EML reference compiler
is included. All third-party research is cited for architectural
context only.
