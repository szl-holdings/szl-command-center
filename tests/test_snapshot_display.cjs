'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

// A small DOM fixture runs the complete renderer and polling flow, without a
// network or browser dependency. Assertions target the status the user sees.
async function render(estate, verticals) {
  const ids = new Map();
  class Element {
    constructor() { this.children = []; this.style = {}; this.attributes = {}; this._text = ''; }
    get firstChild() { return this.children[0]; }
    appendChild(child) { this.children.push(child); return child; }
    removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
    setAttribute(key, value) { this.attributes[key] = value; }
    replaceWith(node) { if (this.id) { ids.set(this.id, node); node.id = this.id; } }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(x => x.textContent).join(''); }
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
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8'), {
    document, window: { location: { host: 'localhost:8000' } },
    setInterval: () => 0,
    fetch: async url => ({ ok: true, json: async () => url.endsWith('/estate') ? estate : verticals }),
  });
  await new Promise(resolve => setImmediate(resolve));
  return ids;
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
  const ids = await render(...fixture(true));
  assert.equal(ids.get('strip-ratio').textContent, '0/5');
  assert.equal(ids.get('strip-state').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('chip-feed').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('chip-verticals').textContent, 'UNAVAILABLE');
  assert.equal(ids.get('snapshot-notice').hidden, false);
  assert.match(ids.get('snapshot-notice').textContent, /2026-09-30T23:27:07Z/);
  assert.match(ids.get('snapshot-notice').textContent, /not used for current status/);
});

test('no historical context leaves the notice hidden', async () => {
  const ids = await render(...fixture(false));
  assert.equal(ids.get('snapshot-notice').hidden, true);
  assert.equal(ids.get('snapshot-notice').textContent, '');
});
