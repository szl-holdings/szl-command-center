/* A distinct read-only front/back witness; never turns source parity into release approval.
   Only textContent is used for untrusted values; no provider mutations. */
(function () {
  'use strict';
  const SCHEMA = 'szl.temporal-convergence-observation/v1';
  const PERIOD_MS = 60000;
  const host = document.getElementById('convergence');
  const chip = document.getElementById('chip-convergence');
  const footer = document.getElementById('foot-convergence');
  if (!host || !chip || !footer) return;

  function node(tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (value !== undefined && value !== null) element.textContent = String(value);
    return element;
  }

  function row(label, state, detail) {
    const card = node('article', 'vcard');
    const h = node('div', 'vcard-head');
    h.appendChild(node('strong', 'vcard-name', label));
    const badge = node('span',
      'chip ' + (state === 'OBSERVED' ? 'chip-green' : 'chip-amber'),
      state === 'OBSERVED' ? 'OBSERVED' : 'NOT PROVEN');
    h.appendChild(badge);
    card.appendChild(h);
    card.appendChild(node('p', 'vcard-mission mono', detail));
    return card;
  }

  function shortSha(value) {
    return typeof value === 'string' && /^[0-9a-f]{40}$/.test(value)
      ? value.slice(0, 12) : 'UNAVAILABLE';
  }

  function valid(data) {
    return data && data.schema === SCHEMA &&
      data.scope === 'UNSIGNED_READ_ONLY_OBSERVATION' &&
      typeof data.production_qualified === 'boolean' &&
      data.production_qualified === false &&
      data.can_deploy === false &&
      Array.isArray(data.gate_vector) && data.gate_vector.length === 4 &&
      Array.isArray(data.blocker_codes) &&
      data.main && data.source && data.storage && data.frontier &&
      /^[0-9a-f]{64}$/.test(data.observation_sha256 || '');
  }

  function show(data) {
    if (!valid(data)) throw new Error('Invalid or overclaiming witness contract');
    host.replaceChildren();
    const gates = data.gate_vector;
    const main = data.main || {};
    const declared = data.source.declared_revisions || {};
    const origins = Object.keys(declared);
    const detail = [
      'main ' + shortSha(main.after),
      origins.map(function (origin) {
        return (origin.indexOf('hf.space') !== -1 ? 'HF' : 'PRODUCT') +
          ' ' + shortSha(declared[origin]);
      }).join(' · '),
      data.source.state || 'UNKNOWN'
    ].join(' · ');
    host.appendChild(row('SOURCE DECLARATIONS',
      gates[0].observed === true ? 'OBSERVED' : 'BLOCKED', detail));

    const sample = ((data.storage.origins || [])[0] || {});
    host.appendChild(row('SEVEN-STORE WRITER',
      gates[1].observed === true ? 'OBSERVED' : 'BLOCKED',
      (data.storage.state || 'UNKNOWN') +
      ' · epoch ' + (sample.epoch ?? '—') +
      ' · ' + (sample.healthy_stores ?? 0) + '/' +
      (sample.required_stores ?? 7) + ' stores'));

    host.appendChild(row('FRONTIER READINESS',
      gates[2].observed === true ? 'OBSERVED' : 'BLOCKED',
      (data.frontier.state || 'UNKNOWN') +
      ' · reported ' + (data.frontier.native_state || 'UNKNOWN')));

    host.appendChild(row('INDEPENDENT EXECUTION AUTHORITY',
      'BLOCKED', 'NOT EVALUATED · no signature or deployment authorization'));

    const failures = data.blocker_codes || [];
    const message = failures.length
      ? 'Current gaps: ' + failures.slice(0, 8).join(' · ') +
        (failures.length > 8 ? ' · +' + (failures.length - 8) + ' more' : '')
      : 'No observed gap; independent execution authority remains unverified';
    host.appendChild(node('p', 'panel-foot mono', message));
    chip.className = 'chip ' +
      (data.observational_convergence === true ? 'chip-green' : 'chip-amber');
    chip.textContent = data.observational_convergence === true
      ? 'OBSERVED CONVERGENCE' : 'CONVERGENCE UNPROVEN';
    footer.textContent = 'Unsigned observation SHA-256 ' +
      data.observation_sha256.slice(0, 20) +
      '… · completed ' + (data.completed_at || 'UNKNOWN') +
      ' · source bytes, signing, restore and payment NOT VERIFIED';
  }

  async function refresh() {
    try {
      const response = await fetch('/api/convergence', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        credentials: 'same-origin'
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      show(await response.json());
    } catch (error) {
      host.replaceChildren();
      host.appendChild(node('p', 'dom-note',
        'CURRENT OBSERVATION UNAVAILABLE: ' + (error.message || 'unknown error')));
      chip.className = 'chip chip-gray';
      chip.textContent = 'UNAVAILABLE';
      footer.textContent = 'No cached or historical witness is promoted when collection fails.';
    }
  }

  refresh();
  setInterval(refresh, PERIOD_MS);
}());
