'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createHash, webcrypto } = require('node:crypto');
const { TextEncoder } = require('node:util');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

// A small DOM fixture runs the complete renderer and polling flow, without a
// network or browser dependency. Assertions target the status the user sees.
async function render(estate, verticals, options = {}) {
  let failed = new Set();
  let poll;
  const requests = [];
  const ids = new Map();
  class Element {
    constructor() { this.children = []; this.style = {}; this.attributes = {}; }
    get firstChild() { return this.children[0]; }
    appendChild(child) { this.children.push(child); return child; }
    removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
    setAttribute(key, value) { this.attributes[key] = value; }
    replaceWith(node) { if (this.id) { ids.set(this.id, node); node.id = this.id; } }
    set textContent(value) { this.children = String(value) ? [{ textContent: String(value) }] : []; }
    get textContent() { return this.children.map(x => x.textContent).join(''); }
  }
  const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
  for (const [, id] of html.matchAll(/\bid="([^"]+)"/g)) {
    const element = new Element(); element.id = id; ids.set(id, element);
  }
  const document = {
    getElementById: id => ids.get(id),
    createElement: () => new Element(),
    createTextNode: text => ({ textContent: text }),
  };
  let source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
  if (options.proxy) source = source.replaceAll('__PORT_8000__', options.proxy);
  vm.runInNewContext(source, {
    document, crypto: options.noCrypto ? undefined : webcrypto, TextEncoder,
    window: { location: { host: options.host || 'localhost:8000' } },
    setInterval: (callback, ms) => { if (ms === 30000) poll = callback; return 0; },
    fetch: async url => {
      requests.push(url);
      // On-demand counterfactual is not part of the three-GET poll.
      if (url.includes('/api/release-impact?')) {
        const permitted = Boolean(options.impact) && !options.impactFailure;
        const response = {
          ok: permitted,
          status: permitted ? 200 : (options.impactFailure || 503),
          json: async () => permitted ? options.impact : { reason_code: 'SOURCE_SNAPSHOT_CHANGED' },
        };
        return response;
      }
      const name = url.endsWith('/estate') ? 'estate' :
        url.endsWith('/ontology') ? 'ontology' : 'verticals';
      // Explicit feature-disabled response is not the same as a failed endpoint.
      const graphFailure = name === 'ontology' &&
        (options.ontologyFailure || failed.has('ontology'));
      const ok = name === 'ontology' ? Boolean(options.ontology) && !graphFailure :
        !failed.has(name);
      const payload = name === 'estate' ? estate :
        name === 'verticals' ? verticals :
          graphFailure ? { reason_code: 'UPSTREAM_FAILURE' } :
            (options.ontology || { reason_code: 'FEATURE_NOT_ADMITTED' });
      const response = { ok, status: ok ? 200 : 503, json: async () => payload };
      if (options.defer && options.defer.enabled) {
        return new Promise(resolve => options.defer.pending.push(() => resolve(response)));
      }
      return response;
    },
  });
  // WebCrypto runs asynchronously; wait for initial paint instead of
  // making a race-dependent assertion after one event-loop tick.
  const painted = () => ['VERIFIED', 'UNKNOWN', 'UNAVAILABLE'].includes(
    ids.get('poll-state').textContent);
  for (let i = 0; i < 100 && !painted(); i++) {
    await new Promise(resolve => setTimeout(resolve, 3));
  }
  assert.ok(painted(), 'initial paint timed out');
  return { ids, requests, startPoll() { return poll(); }, async pollFailures(names) {
    failed = new Set(names);
    await poll();
  }, async pollPayload(name, payload) {
    if (name === 'estate') estate = payload;
    else verticals = payload;
    await poll();
  } };
}

function fixture(withHistory) {
  const estate = {
    generated_at: '2026-11-02T00:00:00Z',
    summary: { panels_total: 5, panels_verified: 0, estate_state: 'UNAVAILABLE' },
    collectors: Object.fromEntries(['github', 'dns', 'cloudflare', 'receipts'].map(
      key => [key, { truth_state: 'UNAVAILABLE', reason: 'current request failed' }]
    )),
  };
  const verticals = { verticals: [{ id: 'test', name: 'Test', truth_state: 'UNAVAILABLE' }] };
  if (withHistory) {
    estate._historical_snapshot = {
      generated_at: '2026-09-30T23:27:07Z',
      summary: { panels_total: 5, panels_verified: 5, estate_state: 'VERIFIED' },
      collectors: { github: { truth_state: 'VERIFIED' } },
    };
  }
  return [estate, verticals];
}

test('historical green evidence cannot promote current rendered status', async () => {
  const { ids } = await render(...fixture(true));
  assert.equal(ids.get('strip-ratio').textContent, '0/5');
  assert.equal(ids.get('strip-state').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('chip-feed').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('chip-verticals').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('snapshot-notice').hidden, false);
  assert.match(ids.get('snapshot-notice').textContent, /2026-09-30T23:27:07Z/);
  assert.match(ids.get('snapshot-notice').textContent, /not used for current status/);
});

test('no historical context leaves the notice hidden', async () => {
  const { ids } = await render(...fixture(false));
  assert.equal(ids.get('snapshot-notice').hidden, true);
  assert.equal(ids.get('snapshot-notice').textContent, '');
});


function healthyFixture() {
  const [estate, verticals] = fixture(false);
  estate.summary = { panels_total: 5, panels_verified: 5, estate_state: 'VERIFIED' };
  Object.values(estate.collectors).forEach(env => { env.truth_state = 'VERIFIED'; delete env.reason; });
  verticals.verticals[0].truth_state = 'VERIFIED';
  return [estate, verticals];
}

test('unmodified source uses same-origin API paths on HTTPS and alternate dev ports', async () => {
  for (const host of ['command.example.test', 'localhost:9000']) {
    const { requests } = await render(...fixture(false), { host });
    assert.deepEqual(requests, ['/api/estate', '/api/verticals', '/api/ontology']);
  }
});

test('a configured preview proxy is preserved', async () => {
  const { requests } = await render(...fixture(false), { host: 'preview.example.test', proxy: 'https://backend.example.test' });
  assert.deepEqual(requests, ['https://backend.example.test/api/estate', 'https://backend.example.test/api/verticals', 'https://backend.example.test/api/ontology']);
});

test('failed estate poll clears previous green chips and counts while verticals remain current', async () => {
  const browser = await render(...healthyFixture());
  const { ids } = browser;
  assert.equal(ids.get('chip-feed').textContent, 'VERIFIED');
  await browser.pollFailures(['estate']);
  for (const id of ['chip-feed', 'chip-domains', 'chip-receipts', 'strip-state']) {
    assert.equal(ids.get(id).textContent, 'UNAVAILABLE', id);
  }
  assert.equal(ids.get('strip-ratio').textContent, '—');
  assert.equal(ids.get('ratio-fill').style.width, '0%');
  assert.equal(ids.get('chip-verticals').textContent, 'VERIFIED');
  assert.match(ids.get('feed').textContent, /HTTP 503/);
  assert.equal(ids.get('poll-state').textContent, 'UNKNOWN');
  await browser.pollFailures([]);
  assert.equal(ids.get('chip-feed').textContent, 'VERIFIED');
  assert.equal(ids.get('strip-ratio').textContent, '5/5');
});

test('failed verticals poll clears previous green card while estate remains current', async () => {
  const browser = await render(...healthyFixture());
  await browser.pollFailures(['verticals']);
  const { ids } = browser;
  assert.equal(ids.get('chip-verticals').textContent, 'UNAVAILABLE');
  assert.match(ids.get('verticals').textContent, /HTTP 503/);
  assert.equal(ids.get('chip-feed').textContent, 'VERIFIED');
  assert.equal(ids.get('strip-ratio').textContent, '5/5');
  assert.equal(ids.get('poll-state').textContent, 'UNKNOWN');
});

test('total outage clears all previously verified status', async () => {
  const browser = await render(...healthyFixture());
  await browser.pollFailures(['estate', 'verticals']);
  for (const id of ['chip-feed', 'chip-domains', 'chip-receipts', 'chip-verticals', 'strip-state', 'poll-state']) {
    assert.equal(browser.ids.get(id).textContent, 'UNAVAILABLE', id);
  }
});


test('empty vertical list is UNKNOWN and never vacuously VERIFIED', async () => {
  const browser = await render(...healthyFixture());
  await browser.pollPayload('verticals', { verticals: [] });
  assert.equal(browser.ids.get('chip-verticals').textContent, 'UNKNOWN');
  assert.match(browser.ids.get('verticals').textContent, /NO VERTICALS/);
});

test('malformed estate responses clear previously verified estate state', async () => {
  const [healthy] = healthyFixture();
  for (const malformed of [null, [], {}, { ...healthy, summary: null }, { ...healthy, collectors: {} }]) {
    const browser = await render(...healthyFixture());
    await browser.pollPayload('estate', malformed);
    assert.equal(browser.ids.get('chip-feed').textContent, 'UNAVAILABLE');
    assert.equal(browser.ids.get('strip-state').textContent, 'UNAVAILABLE');
    assert.equal(browser.ids.get('strip-ratio').textContent, '—');
    assert.match(browser.ids.get('feed').textContent, /Invalid estate response/);
    assert.equal(browser.ids.get('chip-verticals').textContent, 'VERIFIED');
  }
});

test('malformed vertical responses clear previously verified vertical state', async () => {
  for (const malformed of [null, {}, { verticals: {} }, { verticals: [null] }, { verticals: [{truth_state: 'GREEN'}] }]) {
    const browser = await render(...healthyFixture());
    await browser.pollPayload('verticals', malformed);
    assert.equal(browser.ids.get('chip-verticals').textContent, 'UNAVAILABLE');
    assert.match(browser.ids.get('verticals').textContent, /Invalid verticals response/);
    assert.equal(browser.ids.get('chip-feed').textContent, 'VERIFIED');
  }
});


function releaseFabricFixture(graph) {
  const definitions = [
    ['github_source', ['github'], 'IMMUTABLE_SOURCE_CHECKS_AND_REVIEW'],
    ['hf_catalog', ['huggingface'], 'PINNED_MODEL_AND_DATASET_ARTIFACT_BYTES'],
    ['cloudflare_edge', ['cloudflare', 'dns'], 'EXACT_DEPLOYMENT_AND_RULE_READBACK'],
    ['receipt_index', ['receipts'], 'INDEPENDENTLY_VERIFIED_RECEIPT_AUTHORITY'],
    ['model_evaluation', [], 'WEIGHT_BOUND_MEASUREMENTS_AND_BASELINES'],
    ['runtime_deployment', [], 'SOURCE_MATCHED_EXTERNAL_RUNTIME_AND_AUTH'],
    ['payment_settlement', [], 'FACILITATOR_CHAIN_AND_PAYOUT_RECONCILIATION'],
    ['pypi_distribution', [], 'PEP740_WHEEL_SDIST_TAG_AND_SOURCE_MATCH']
  ];
  const rules = [
    ['github_source', 'hf_catalog', 'GITHUB_TO_HF_ARTIFACT_BINDING'],
    ['github_source', 'cloudflare_edge', 'SOURCE_TO_EDGE_CONFIG_BINDING'],
    ['github_source', 'pypi_distribution', 'SOURCE_TO_PACKAGE_PROVENANCE_BINDING'],
    ['hf_catalog', 'model_evaluation', 'WEIGHTS_TO_EVALUATION_BINDING'],
    ['hf_catalog', 'runtime_deployment', 'WEIGHTS_TO_RUNTIME_BINDING'],
    ['cloudflare_edge', 'runtime_deployment', 'EDGE_TO_RUNTIME_IDENTITY_BINDING'],
    ['receipt_index', 'model_evaluation', 'RECEIPT_TO_EVALUATION_BINDING'],
    ['receipt_index', 'payment_settlement', 'RECEIPT_TO_SETTLEMENT_BINDING'],
    ['runtime_deployment', 'payment_settlement', 'RUNTIME_TO_SETTLEMENT_BINDING']
  ];
  const sources = Object.fromEntries(graph.nodes.slice(1).map(n => [n.label, n.truth_state]));
  const stages = definitions.map(function ([id, collectors, required_gate]) {
    const values = collectors.map(x => sources[x] || 'UNAVAILABLE');
    const collector_state = !values.length || values.every(x => x === 'UNAVAILABLE')
      ? 'UNAVAILABLE' : values.every(x => x === 'VERIFIED') ? 'VERIFIED' : 'UNKNOWN';
    return { id, kind: 'release_stage', collectors, required_gate, collector_state,
      collector_scope: collectors.length ? 'EXISTING_METADATA_ONLY' : 'NO_ADMITTED_COLLECTOR',
      qualification: 'NOT_ESTABLISHED', can_execute_actions: false };
  });
  return {
    schema: 'szl.readonly.release_fabric.v1',
    scope: 'SOURCE_COVERAGE_AND_RELEASE_REQUIREMENTS_ONLY',
    basis_source_snapshot_sha256: graph.source_snapshot_sha256,
    authority: 'READ_ONLY_NO_APPROVAL',
    production_qualified: false, can_deploy: false,
    financial_revenue_verified: false, fingerprint_is_signature: false,
    independently_qualified_stages: 0,
    stage_count: stages.length, unverified_dependency_count: rules.length,
    collector_verified_stages: stages.filter(x => x.collector_state === 'VERIFIED').length,
    stages,
    dependencies: rules.map(function ([source, target, required_binding]) {
      return { source, target, required_binding, evidence_state: 'NOT_ESTABLISHED',
        action_authorized: false };
    }),
    content_sha256: 'c'.repeat(64)
  };
}

function canonicalForFixture(value) {
  if (value === null) return 'null';
  if (typeof value === 'string') {
    return JSON.stringify(value).replace(/[\u007f-\uffff]/g, c =>
      '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
  }
  if (typeof value === 'number' || typeof value === 'boolean') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalForFixture).join(',') + ']';
  if (typeof value === 'object') return '{' + Object.keys(value).sort().map(
    key => canonicalForFixture(key) + ':' + canonicalForFixture(value[key])).join(',') + '}';
  throw new Error('Unsupported fixture input');
}

function digestFixture(value) {
  return createHash('sha256').update(canonicalForFixture(value), 'utf8').digest('hex');
}

function recomputeGraphChecksums(graph) {
  const sourceBody = {
    source_generated_at: graph.source_generated_at,
    observations: graph.nodes.slice(1).map(node => [
      node.id, node.truth_state, node.observed_at, node.evidence_ref_sha256,
    ]),
  };
  graph.source_snapshot_sha256 = digestFixture(sourceBody);
  graph.release_fabric.basis_source_snapshot_sha256 = graph.source_snapshot_sha256;
  const { content_sha256: ignoredFabric, ...fabricBody } = graph.release_fabric;
  graph.release_fabric.content_sha256 = digestFixture(fabricBody);
  const { content_sha256: ignoredOuter, ...outerBody } = graph;
  graph.content_sha256 = digestFixture(outerBody);
  return graph;
}

function graphFixture(estate, sourceStamp = estate.generated_at) {
  const sources = ['github', 'huggingface', 'cloudflare', 'dns', 'receipts'];
  const graph = {
    schema: 'szl.readonly.evidence_graph.v1',
    source_generated_at: sourceStamp,
    source_snapshot_sha256: 'a'.repeat(64),
    content_sha256: 'b'.repeat(64),
    rollup: 'UNKNOWN',
    authorization: { mode: 'READ_ONLY', can_execute_actions: false },
    provenance: { snapshot_signature: 'NOT_ESTABLISHED' },
    total_sources: 5, verified_sources: 0,
    links: sources.map(name => ({ source: 'source:' + name,
      target: 'snapshot:estate', kind: 'observed_in' })),
    nodes: [{ kind: 'snapshot', id: 'snapshot:estate', action_authorized: false }, ...sources.map(
      name => ({ id: 'source:' + name, kind: 'evidence_source',
        label: name, truth_state: 'UNKNOWN', reason_code: 'SYNTHETIC',
        observed_at: null, evidence_ref_sha256: null,
        action_authorized: false }))
    ],
  };
  graph.release_fabric = releaseFabricFixture(graph);
  return recomputeGraphChecksums(graph);
}

test('disabled evidence graph leaves historical successes unpromoted', async () => {
  const [estate, verticals] = fixture(true);
  const { ids, requests } = await render(estate, verticals);
  assert.deepEqual(requests, ['/api/estate', '/api/verticals', '/api/ontology']);
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
  assert.match(ids.get('ontology-graph').textContent, /FEATURE_NOT_ADMITTED_OR_UNAVAILABLE/);
  assert.equal(ids.get('strip-state').textContent, 'UNAVAILABLE');
});

test('feature-disabled graph preserves independently verified base dashboard', async () => {
  const { ids } = await render(...healthyFixture());
  assert.equal(ids.get('strip-state').textContent, 'VERIFIED');
  assert.equal(ids.get('poll-state').textContent, 'VERIFIED');
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
});

test('unexpected ontology outage downgrades otherwise verified base dashboard', async () => {
  const [estate, verticals] = healthyFixture();
  const { ids } = await render(estate, verticals, { ontologyFailure: true });
  assert.equal(ids.get('strip-state').textContent, 'VERIFIED');
  assert.equal(ids.get('poll-state').textContent, 'UNKNOWN');
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
});

test('admitted verified matching graph preserves independently verified base dashboard', async () => {
  const [estate, verticals] = healthyFixture();
  const graph = graphFixture(estate);
  graph.rollup = 'VERIFIED';
  graph.verified_sources = 5;
  graph.nodes.slice(1).forEach(function (node) { node.truth_state = 'VERIFIED'; });
  graph.release_fabric = releaseFabricFixture(graph);
  recomputeGraphChecksums(graph);
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.equal(ids.get('poll-state').textContent, 'VERIFIED');
  assert.equal(ids.get('ontology-chip').textContent, 'VERIFIED');
});

test('source-matched read-only ontology graph renders five evidence sources', async () => {
  const [estate, verticals] = fixture(false);
  const graph = graphFixture(estate);
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.equal(ids.get('ontology-chip').textContent, 'UNKNOWN');
  assert.match(ids.get('ontology-foot').textContent, /actions: DENIED/);
  const content = ids.get('ontology-graph').textContent;
  for (const name of ['github', 'huggingface', 'cloudflare', 'dns', 'receipts']) {
    assert.match(content, new RegExp(name));
  }
  assert.doesNotMatch(content, /production.ready/i);
  assert.match(content, /ONE RELEASE CHAIN/);
  assert.match(content, /0\/8 independently qualified/);
  assert.match(content, /0\/9 links proven/);
  assert.match(content, /GitHub source/);
  assert.match(content, /Hugging Face artifacts/);
  assert.match(content, /Cloudflare \/ DNS/);
  assert.match(content, /x402 settlement/);
  assert.match(content, /PyPI release/);
  assert.match(content, /NOT ESTABLISHED/);
});

test('source snapshot mismatch is visibly unavailable rather than silently reused', async () => {
  const [estate, verticals] = healthyFixture();
  const graph = graphFixture(estate, '2000-01-01T00:00:00Z');
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
  assert.match(ids.get('ontology-graph').textContent, /SOURCE_SNAPSHOT_MISMATCH/);
  assert.equal(ids.get('poll-state').textContent, 'UNKNOWN');
});

test('malformed ontology digest cannot promote status or throw an uncaught error', async () => {
  const [estate, verticals] = healthyFixture();
  const graph = graphFixture(estate);
  graph.rollup = 'VERIFIED';
  graph.source_snapshot_sha256 = null;
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('poll-state').textContent, 'UNKNOWN');
});

test('duplicate graph source or missing edge cannot promote verified', async () => {
  const [estate, verticals] = healthyFixture();
  const graph = graphFixture(estate);
  graph.rollup = 'VERIFIED';
  graph.verified_sources = 5;
  graph.nodes.slice(1).forEach(function (node) { node.truth_state = 'VERIFIED'; });
  graph.nodes[2].id = graph.nodes[1].id;
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('poll-state').textContent, 'UNKNOWN');
});

test('older overlapping poll cannot repaint after newer failed observation', async () => {
  const deferred = { enabled: false, pending: [] };
  const browser = await render(...healthyFixture(), { defer: deferred });
  assert.equal(browser.ids.get('poll-state').textContent, 'VERIFIED');
  deferred.enabled = true;
  const older = browser.startPoll();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(deferred.pending.length, 3);
  deferred.enabled = false;
  await browser.pollFailures(['estate']);
  assert.equal(browser.ids.get('strip-state').textContent, 'UNAVAILABLE');
  assert.equal(browser.ids.get('poll-state').textContent, 'UNKNOWN');
  deferred.pending.forEach(resolve => resolve());
  await older;
  assert.equal(browser.ids.get('strip-state').textContent, 'UNAVAILABLE');
  assert.equal(browser.ids.get('poll-state').textContent, 'UNKNOWN');
});

test('ontology cannot grant actions through a fabricated authorization flag', async () => {
  const [estate, verticals] = fixture(false);
  const graph = graphFixture(estate);
  graph.authorization.can_execute_actions = true;
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
});

test('release fabric rejects attempted release, payment or execution promotion', async () => {
  const corruptions = [
    fabric => { fabric.production_qualified = true; },
    fabric => { fabric.can_deploy = true; },
    fabric => { fabric.financial_revenue_verified = true; },
    fabric => { fabric.independently_qualified_stages = 1; },
    fabric => { fabric.stages[7].qualification = 'QUALIFIED'; },
    fabric => { fabric.stages[6].collector_state = 'VERIFIED'; },
    fabric => { fabric.dependencies[0].evidence_state = 'PROVEN'; },
    fabric => { fabric.dependencies[2].action_authorized = true; },
    fabric => { fabric.basis_source_snapshot_sha256 = 'f'.repeat(64); },
    fabric => { fabric.fingerprint_is_signature = true; },
    fabric => { fabric.dependencies.pop(); },
  ];
  for (const corrupt of corruptions) {
    const [estate, verticals] = healthyFixture();
    const graph = graphFixture(estate);
    corrupt(graph.release_fabric);
    const { ids } = await render(estate, verticals, { ontology: graph });
    assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
    assert.match(ids.get('ontology-graph').textContent, /FEATURE_NOT_ADMITTED_OR_UNAVAILABLE|INVALID_GRAPH_CONTRACT|GRAPH_CHECKSUM_UNVERIFIED/);
    assert.doesNotMatch(ids.get('ontology-graph').textContent, /GATE NOT ESTABLISHED/);
  }
});

test('release fabric never enables public-preview private collectors', async () => {
  const [estate, verticals] = fixture(false);
  const graph = graphFixture(estate);
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.match(ids.get('ontology-graph').textContent, /NO_ADMITTED_COLLECTOR|GATE NOT ESTABLISHED/);
  assert.doesNotMatch(ids.get('ontology-graph').textContent, /private.customer|payment.signature/i);
});


test('real Python-generated ontology SHA-256 fixture passes the browser checksum gate', async () => {
  const raw = fs.readFileSync(
    path.join(__dirname, 'fixtures/release-fabric-python-golden.v1.json'));
  // Git may check out JSON with CRLF on Windows; pin the canonical LF blob.
  const canonicalBytes = Buffer.from(raw.toString('utf8').replace(/\r\n/g, '\n'), 'utf8');
  assert.equal(createHash('sha256').update(canonicalBytes).digest('hex'),
    '9867c97ca5d3247cbd3380044cdbab0e5cb2cc64c394be1b23d8ef0c20c66eaf');
  const graph = JSON.parse(raw);
  assert.equal(graph.source_snapshot_sha256,
    '9e36590d321c0afbf0b1c3847bbb7787819e84f491a1ef0cd94d0383847f9bbf');
  assert.equal(graph.release_fabric.content_sha256,
    'a7c0101687f99dd62921833d3ea44706b58e153201dab1a760fc4f7bbda71a92');
  const [estate, verticals] = fixture(false);
  estate.generated_at = graph.source_generated_at;
  const { ids } = await render(estate, verticals, { ontology: graph });
  assert.equal(ids.get('ontology-chip').textContent, 'VERIFIED');
  assert.match(ids.get('ontology-graph').textContent, /ONE RELEASE CHAIN/);
  assert.match(ids.get('ontology-graph').textContent, /0\/8 independently qualified/);
});

test('each of the three independent hash bindings rejects structurally plausible tampering', async () => {
  const source = fs.readFileSync(
    path.join(__dirname, 'fixtures/release-fabric-python-golden.v1.json'));
  const attacks = [
    ['source', graph => { graph.nodes[1].evidence_ref_sha256 = 'f'.repeat(64); }],
    ['fabric', graph => { graph.release_fabric.limitations += ' tampered'; }],
    ['outer', graph => { graph.provenance.runtime_production_ready = 'QUALIFIED'; }],
  ];
  for (const [axis, attack] of attacks) {
    const graph = JSON.parse(source);
    attack(graph);
    const [estate, verticals] = fixture(false);
    estate.generated_at = graph.source_generated_at;
    const { ids } = await render(estate, verticals, { ontology: graph });
    assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE', axis);
    assert.match(ids.get('ontology-graph').textContent,
      /GRAPH_CHECKSUM_UNVERIFIED/, axis);
    assert.doesNotMatch(ids.get('ontology-graph').textContent,
      /ONE RELEASE CHAIN/, axis);
  }
});

test('WebCrypto unavailable fails closed instead of trusting formatted SHA-256 values', async () => {
  const graph = JSON.parse(fs.readFileSync(
    path.join(__dirname, 'fixtures/release-fabric-python-golden.v1.json')));
  const [estate, verticals] = fixture(false);
  estate.generated_at = graph.source_generated_at;
  const { ids } = await render(estate, verticals, { ontology: graph, noCrypto: true });
  assert.equal(ids.get('ontology-chip').textContent, 'UNAVAILABLE');
  assert.match(ids.get('ontology-graph').textContent, /GRAPH_CHECKSUM_UNVERIFIED/);
  assert.equal(ids.get('poll-state').textContent, 'UNKNOWN');
});

function descendants(root) {
  const result = [];
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    result.push(node);
    (node.children || []).forEach(visit);
  }
  visit(root);
  return result;
}

test('on-demand release-impact rehearsal binds the Python fixture and changes no authority', async () => {
  const root = path.join(__dirname, 'fixtures');
  const graph = JSON.parse(fs.readFileSync(path.join(root, 'release-fabric-python-golden.v1.json')));
  const impactRaw = fs.readFileSync(path.join(root, 'release-impact-python-golden.v1.json'));
  assert.equal(createHash('sha256').update(Buffer.from(impactRaw.toString().replace(/\r\n/g, '\n'))).digest('hex'),
    '37bc31dfd642f679ff253b568be48d8df12111837791cd96208d8f2e89907427');
  const impact = JSON.parse(impactRaw);
  assert.equal(impact.content_sha256,
    '6db2731329a0d1156383eac5b4a70056962c065c2da23d29a8adafb34cebfe61');
  const [estate, verticals] = fixture(false);
  estate.generated_at = graph.source_generated_at;
  const browser = await render(estate, verticals, { ontology: graph, impact });
  assert.equal(browser.requests.length, 3, 'no impact request on initial poll');
  const nodes = descendants(browser.ids.get('ontology-graph'));
  const button = nodes.find(x => x.textContent === 'Rehearse loss' && typeof x.onclick === 'function');
  const status = nodes.find(x => x.className === 'mono release-impact-result');
  assert.ok(button && status);
  assert.match(status.textContent, /NOT RUN/);
  await button.onclick();
  assert.equal(browser.requests.length, 4, 'exactly one user-directed impact GET');
  assert.match(browser.requests[3], /\/api\/release-impact\?source=github&basis=/);
  assert.match(browser.requests[3], new RegExp(graph.source_snapshot_sha256));
  assert.match(status.textContent, /7 structurally exposed/);
  assert.match(status.textContent, /1 metadata stages change/);
  assert.match(status.textContent, /All links remain unproved/);
  assert.match(status.textContent, /No actions, deployment or revenue authorized/);
  assert.equal(browser.ids.get('ontology-chip').textContent, 'VERIFIED');
});

test('a tampered impact result cannot become a new permission or green claim', async () => {
  const graph = JSON.parse(fs.readFileSync(
    path.join(__dirname, 'fixtures/release-fabric-python-golden.v1.json')));
  const valid = JSON.parse(fs.readFileSync(
    path.join(__dirname, 'fixtures/release-impact-python-golden.v1.json')));
  for (const scenario of [
    { ...valid, can_deploy: true },
    { ...valid, production_qualified: true },
    { ...valid, action_authorized: true },
    { ...valid, interpretation: 'Modified without corresponding checksum' },
    { ...valid, basis_source_snapshot_sha256: 'f'.repeat(64) },
  ]) {
    const [estate, verticals] = fixture(false);
    estate.generated_at = graph.source_generated_at;
    const browser = await render(estate, verticals, { ontology: graph, impact: scenario });
    const nodes = descendants(browser.ids.get('ontology-graph'));
    const button = nodes.find(x => x.textContent === 'Rehearse loss' && typeof x.onclick === 'function');
    const status = nodes.find(x => x.className === 'mono release-impact-result');
    assert.ok(button);
    await button.onclick();
    assert.match(status.textContent, /UNAVAILABLE · IMPACT_(CONTRACT|CHECKSUM)_INVALID/);
    assert.doesNotMatch(status.textContent, /7 structurally exposed/);
    assert.equal(browser.ids.get('ontology-chip').textContent, 'VERIFIED');
  }
});

test('stale impact source refuses to reuse previous simulated success', async () => {
  const graph = JSON.parse(fs.readFileSync(
    path.join(__dirname, 'fixtures/release-fabric-python-golden.v1.json')));
  const [estate, verticals] = fixture(false);
  estate.generated_at = graph.source_generated_at;
  const browser = await render(estate, verticals, { ontology: graph, impactFailure: 409 });
  const nodes = descendants(browser.ids.get('ontology-graph'));
  const button = nodes.find(x => x.textContent === 'Rehearse loss' && typeof x.onclick === 'function');
  const status = nodes.find(x => x.className === 'mono release-impact-result');
  await button.onclick();
  assert.match(status.textContent, /SOURCE_SNAPSHOT_CHANGED/);
  assert.doesNotMatch(status.textContent, /exposed:/);
});
