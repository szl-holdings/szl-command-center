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
      const name = url.endsWith('/estate') ? 'estate' : 'verticals';
      return { ok: !failed.has(name), status: 503, json: async () => name === 'estate' ? estate : verticals };
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  return { ids, requests, async pollFailures(names) {
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
    assert.deepEqual(requests, ['/api/estate', '/api/verticals']);
  }
});

test('a configured preview proxy is preserved', async () => {
  const { requests } = await render(...fixture(false), { host: 'preview.example.test', proxy: 'https://backend.example.test' });
  assert.deepEqual(requests, ['https://backend.example.test/api/estate', 'https://backend.example.test/api/verticals']);
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
