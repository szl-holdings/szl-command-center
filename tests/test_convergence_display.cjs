/* Node-native DOM simulation: real renderer, success then fail-closed refresh. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'frontend', 'convergence.js'), 'utf8'
);

class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.textContent = '';
    this.className = '';
  }
  appendChild(element) {
    this.children.push(element);
    return element;
  }
  replaceChildren(...elements) {
    this.children = elements;
  }
}

function payload() {
  const head = 'a'.repeat(40);
  return {
    schema: 'szl.temporal-convergence-observation/v1',
    scope: 'UNSIGNED_READ_ONLY_OBSERVATION',
    main: { before: head, after: head },
    source: {
      state: 'DECLARATIONS_MATCH',
      declared_revisions: {
        'https://szlholdings-a11oy.hf.space': head,
        'https://a-11-oy.com': head,
      },
    },
    storage: { state: 'HEALTHY_REPORTED', origins: [
      { epoch: 291, healthy_stores: 7, required_stores: 7 },
      { epoch: 291, healthy_stores: 7, required_stores: 7 },
    ] },
    frontier: { state: 'NOT_READY_OR_UNKNOWN', native_state: 'NOT_READY' },
    observational_convergence: true,
    production_qualified: false,
    can_deploy: false,
    gate_vector: [
      { gate: 'SOURCE_DECLARATIONS', observed: true },
      { gate: 'STATE_PRESERVATION', observed: true },
      { gate: 'FRONTIER_READINESS', observed: false },
      { gate: 'EXECUTION_AUTHORITY', observed: false },
    ],
    blocker_codes: ['INDEPENDENT_EXECUTION_PROOF_NOT_VERIFIED'],
    observation_sha256: 'b'.repeat(64),
    completed_at: '2026-11-17T05:00:00Z',
  };
}

function harness() {
  const elements = {
    convergence: new Element('div'),
    'chip-convergence': new Element('span'),
    'foot-convergence': new Element('footer'),
  };
  let getResponse = async () => ({ ok: true, json: async () => payload() });
  let callback;
  const requests = [];
  const context = {
    document: {
      getElementById(id) { return elements[id] || null; },
      createElement(tag) { return new Element(tag); },
    },
    fetch(url, options) {
      requests.push({ url, options });
      return getResponse();
    },
    setInterval(fn, ms) { callback = fn; assert.equal(ms, 60000); },
  };
  vm.runInNewContext(src, context);
  return {
    elements, requests,
    setResponse(fn) { getResponse = fn; },
    tick() { return callback(); },
  };
}

function flush() {
  return new Promise(resolve => setImmediate(resolve));
}

test('source/storage evidence is shown without execution approval', async () => {
  const h = harness();
  await flush();
  assert.equal(h.requests[0].url, '/api/convergence');
  assert.equal(h.elements.convergence.children.length, 5);
  assert.equal(h.elements['chip-convergence'].textContent, 'OBSERVED CONVERGENCE');
  assert.match(h.elements['foot-convergence'].textContent, /NOT VERIFIED/);
  assert.match(h.elements.convergence.children[3].children[1].textContent,
               /no signature or deployment authorization/);
  assert.doesNotMatch(src, /\.innerHTML\s*=/);
});

test('unavailable refresh immediately clears old evidence', async () => {
  const h = harness();
  await flush();
  h.setResponse(async () => ({ ok: false, status: 503 }));
  await h.tick();
  assert.equal(h.elements.convergence.children.length, 1);
  assert.equal(h.elements['chip-convergence'].textContent, 'UNAVAILABLE');
  assert.match(h.elements.convergence.children[0].textContent, /HTTP 503/);
});

test('a malicious production-qualifying payload fails closed', async () => {
  const h = harness();
  await flush();
  h.setResponse(async () => ({
    ok: true,
    json: async () => ({ ...payload(), production_qualified: true }),
  }));
  await h.tick();
  assert.equal(h.elements['chip-convergence'].textContent, 'UNAVAILABLE');
  assert.match(h.elements.convergence.children[0].textContent, /overclaiming/);
});
