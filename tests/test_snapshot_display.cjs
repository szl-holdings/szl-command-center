'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
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
    document, window: { location: { host: options.host || 'localhost:8000' } },
    setInterval: (callback, ms) => { if (ms === 30000) poll = callback; return 0; },
    fetch: async url => {
      requests.push(url);
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
  await new Promise(resolve => setImmediate(resolve));
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


function graphFixture(estate, sourceStamp = estate.generated_at) {
  const sources = ['github', 'huggingface', 'cloudflare', 'dns', 'receipts'];
  return {
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
        action_authorized: false }))
    ],
  };
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
