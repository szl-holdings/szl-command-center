/* SZL Command Center — frontend renderer.
   Fetches /api/estate and /api/verticals, renders truth-state panels.
   Polls every 30s. Nothing renders without a state. */
(function () {
  'use strict';

  var THEME = {
    VERIFIED: { cls: 'chip-green', label: 'VERIFIED' },
    UNKNOWN: { cls: 'chip-amber', label: 'UNKNOWN' },
    UNAVAILABLE: { cls: 'chip-gray', label: 'UNAVAILABLE' },
  };

  var POLL_MS = 30000;
  var lastEstate = null;
  var lastVerticals = null;

  function el(id) {
    return document.getElementById(id);
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function text(s) {
    return document.createTextNode(s == null ? '' : String(s));
  }

  function chip(state) {
    var t = THEME[state] || THEME.UNAVAILABLE;
    var s = document.createElement('span');
    s.className = 'chip ' + t.cls;
    s.textContent = t.label;
    return s;
  }

  /* Number of seconds between ts and now, computed once per call-site set. */
  function parseTs(ts) {
    if (!ts) return NaN;
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(ts)) ts = ts.replace(' ', 'T') + 'Z';
    return Date.parse(ts);
  }

  function timeAgo(ts, now) {
    var t = parseTs(ts);
    if (isNaN(t)) return ts ? String(ts).slice(0, 10) : '—';
    var s = Math.max(0, Math.floor((now - t) / 1000));
    if (s < 45) return 'now';
    if (s < 90) return '1m ago';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    if (s < 5400) return '1h ago';
    if (s < 86400) return Math.floor(s / 3600) + 'h ago';
    if (s < 129600) return '1d ago';
    return Math.floor(s / 86400) + 'd ago';
  }

  function escReason(env) {
    if (!env) return '';
    return env.reason ? env.reason : '';
  }

  function errBlock(title, reason, ref) {
    var d = document.createElement('div');
    d.className = 'err';
    var b = document.createElement('b');
    b.textContent = title;
    d.appendChild(b);
    var p = document.createElement('span');
    p.textContent = reason || 'no reason recorded';
    d.appendChild(p);
    if (ref) {
      var c = document.createElement('code');
      c.textContent = ref;
      d.appendChild(c);
    }
    return d;
  }

  function setFoot(id, env) {
    var foot = el(id);
    clear(foot);
    if (!env) return;
    var parts = [];
    parts.push('evidence: ' + (env.evidence_ref || '—'));
    parts.push('observed ' + (env.verified_at || '—'));
    if (env.reason) parts.push('reason: ' + env.reason);
    foot.appendChild(text(parts.join(' · ')));
  }

  function panelChip(id, result) {
    var c = el(id);
    var state = result.ok ? 'VERIFIED' : result.partial ? 'UNKNOWN' : 'UNAVAILABLE';
    var repl = chip(state);
    c.replaceWith(repl);
    repl.id = id;
  }

  /* ---------- top strip ---------- */

  function renderStrip(estate, verticals) {
    var now = Date.now();
    var sum = estate.summary || {};
    var total = sum.panels_total || 0;
    var verified = sum.panels_verified || 0;
    var ratio = total ? verified / total : 0;

    var r = el('strip-ratio');
    clear(r);
    r.appendChild(text(verified + '/' + total));

    el('ratio-fill').style.width = Math.round(ratio * 100) + '%';

    var st = el('strip-state');
    clear(st);
    st.appendChild(chip(sum.estate_state || 'UNAVAILABLE'));

    var iss = el('strip-issues');
    clear(iss);
    var gh = estate.collectors && estate.collectors.github;
    var issuesEnv = gh && gh.value ? gh.value.open_issues : null;
    if (issuesEnv && issuesEnv.truth_state === 'VERIFIED' && issuesEnv.value) {
      var v = issuesEnv.value;
      iss.appendChild(text(v.total + (v.truncated ? '+' : '')));
    } else {
      iss.appendChild(text('—'));
    }

    var head = el('strip-head');
    clear(head);
    var headEnv = gh && gh.value && gh.value.flagship ? gh.value.flagship.head : null;
    if (headEnv && headEnv.truth_state === 'VERIFIED' && headEnv.value && headEnv.value.sha) {
      head.appendChild(text(headEnv.value.sha + ' · ' + timeAgo(headEnv.value.committed_at, now)));
      head.title = headEnv.value.message || '';
    } else {
      head.appendChild(text('—'));
      if (headEnv && headEnv.reason) head.title = headEnv.reason;
    }

    el('strip-refresh').textContent = timeAgo(estate.generated_at, now);
  }

  /* ---------- verticals ---------- */

  function runDot(conclusion, status) {
    var d = document.createElement('span');
    var cls = 'rdot-none';
    if (conclusion === 'success') cls = 'rdot-success';
    else if (conclusion === 'failure') cls = 'rdot-failure';
    else if (conclusion || (status && status !== 'completed')) cls = 'rdot-pending';
    d.className = 'rdot ' + cls;
    return d;
  }

  function repoRow(repo) {
    var row = document.createElement('div');
    row.className = 'vrepo';

    var left = document.createElement('span');
    left.className = 'vrepo-name';
    var latest = repo.latest_run || {};
    var rollup = repo.workflow_rollup || {};
    var dotConclusion = latest.conclusion;
    var dotStatus = latest.status;
    if (rollup.ci === 'failure') {
      dotConclusion = 'failure';
      dotStatus = 'completed';
    }
    left.appendChild(runDot(dotConclusion, dotStatus));
    var name = document.createElement('span');
    name.textContent = repo.repo;
    var meta = repo.meta || {};
    if (meta.truth_state === 'VERIFIED' && meta.value && meta.value.url) {
      var a = document.createElement('a');
      a.href = meta.value.url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.appendChild(name);
      left.appendChild(a);
    } else {
      left.appendChild(name);
    }
    if (meta.truth_state === 'VERIFIED' && meta.value && meta.value.archived) {
      var tag = document.createElement('span');
      tag.className = 'chip chip-gray';
      tag.textContent = 'ARCHIVED';
      left.appendChild(text(' '));
      left.appendChild(tag);
    }
    row.appendChild(left);

    var right = document.createElement('span');
    if (repo.open_issues != null) right.textContent = repo.open_issues + ' open';
    else right.textContent = '·';
    row.appendChild(right);

    var titles = [];
    if (latest.workflowName) titles.push(latest.workflowName + ' → ' + (latest.conclusion || latest.status || '?'));
    if (rollup && rollup.failing_workflows && rollup.failing_workflows.length) {
      titles.push('failing workflows: ' + rollup.failing_workflows.join(', '));
    }
    if (rollup && rollup.protected_merge_readiness === false) {
      titles.push('not protected-merge readiness');
    }
    if (meta.reason) titles.push('meta: ' + meta.reason);
    if (repo.ci && repo.ci.reason) titles.push('ci: ' + repo.ci.reason);
    if (titles.length) row.title = titles.join(' | ');
    return row;
  }

  function renderVerticals(data) {
    var host = el('verticals');
    clear(host);
    if (!data || !data.verticals || !data.verticals.length) {
      host.appendChild(errBlock('NO VERTICALS', 'the /api/verticals payload carried no verticals', null));
      return;
    }
    var now = Date.now();
    data.verticals.forEach(function (v) {
      var card = document.createElement('article');
      card.className = 'vcard health-' + ((v.value && v.value.health) || 'unknown');
      card.setAttribute('data-testid', 'card-vertical-' + v.id);

      var head = document.createElement('div');
      head.className = 'vcard-head';
      var left = document.createElement('span');
      left.className = 'vcard-title';
      var dot = document.createElement('span');
      var health = (v.value && v.value.health) || 'unknown';
      dot.className = 'dot dot-' + health;
      dot.title = 'health: ' + health;
      left.appendChild(dot);
      var nm = document.createElement('span');
      nm.className = 'vcard-name';
      nm.textContent = v.name;
      left.appendChild(nm);
      head.appendChild(left);
      head.appendChild(chip(v.truth_state));
      card.appendChild(head);

      var mission = document.createElement('p');
      mission.className = 'vcard-mission';
      mission.textContent = v.mission || '';
      card.appendChild(mission);

      var stats = document.createElement('div');
      stats.className = 'vcard-stats';
      function stat(num, label) {
        var s = document.createElement('span');
        s.className = 'vstat';
        var b = document.createElement('b');
        b.textContent = num;
        var l = document.createElement('span');
        l.textContent = label;
        s.appendChild(b);
        s.appendChild(l);
        return s;
      }
      var val = v.value || {};
      stats.appendChild(stat(val.repos ? val.repos.length : 0, 'REPOS'));
      stats.appendChild(stat(val.open_issues != null ? val.open_issues : '—', 'OPEN ISSUES'));
      stats.appendChild(stat(val.last_push ? timeAgo(val.last_push, now) : '—', 'LAST PUSH'));
      card.appendChild(stats);

      var repos = document.createElement('div');
      repos.className = 'vrepos';
      (val.repos || []).slice(0, 6).forEach(function (r) {
        repos.appendChild(repoRow(r));
      });
      if (!val.repos || !val.repos.length) repos.appendChild(text('no repos observed'));
      card.appendChild(repos);

      if (v.reason) {
        var note = document.createElement('p');
        note.className = 'vnote';
        note.textContent = v.reason;
        card.appendChild(note);
      }

      host.appendChild(card);
    });
  }

  /* ---------- governance feed ---------- */

  function feedRow(run, repo, now) {
    var row = document.createElement('div');
    row.className = 'feed-row';

    var when = document.createElement('span');
    when.className = 'feed-when';
    when.textContent = timeAgo(run.updatedAt, now);
    row.appendChild(when);

    var what = document.createElement('span');
    what.className = 'feed-what';
    if (run.url) {
      var a = document.createElement('a');
      a.href = run.url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.style.color = 'inherit';
      a.style.textDecoration = 'none';
      a.appendChild(text((run.workflowName || 'workflow')));
      what.appendChild(a);
    } else {
      what.appendChild(text(run.workflowName || 'workflow'));
    }
    what.title = (run.workflowName || '') + ' · ' + (run.conclusion || run.status || '?');
    row.appendChild(what);

    var sha = document.createElement('span');
    sha.className = 'feed-sha';
    sha.textContent = run.head_sha || '';
    row.appendChild(sha);

    var st = document.createElement('span');
    var conclusion = run.conclusion || '';
    if (conclusion === 'success') {
      st.className = 'chip chip-green';
      st.textContent = 'SUCCESS';
    } else if (conclusion === 'failure') {
      st.className = 'chip chip-red';
      st.textContent = 'FAILURE';
    } else if (run.status && run.status !== 'completed') {
      st.className = 'chip chip-amber';
      st.textContent = String(run.status).toUpperCase();
    } else {
      st.className = 'chip chip-gray';
      st.textContent = (conclusion || 'NO SIGNAL').toUpperCase();
    }
    row.appendChild(st);
    return row;
  }

  function renderFeed(estate, verticals) {
    var host = el('feed');
    clear(host);
    var now = Date.now();

    /* gates ledger from receipt verification states */
    var rc = estate.collectors && estate.collectors.receipts;
    var gates = null;
    if (rc && rc.value && rc.value.verification && rc.value.verification.value) {
      gates = rc.value.verification.value.checks || [];
    }

    var anyRows = false;
    if (verticals && verticals.verticals) {
      verticals.verticals.forEach(function (v) {
        var repos = (v.value && v.value.repos) || [];
        var withRuns = repos.filter(function (r) { return r.latest_run; });
        if (!withRuns.length) return;
        var hd = document.createElement('div');
        hd.className = 'feed-repoheader';
        var nm = document.createElement('span');
        nm.textContent = v.name.toUpperCase();
        hd.appendChild(nm);
        var lead = document.createElement('span');
        lead.className = 'lead';
        lead.textContent = 'observed CI — not merge readiness';
        hd.appendChild(lead);
        host.appendChild(hd);
        withRuns.forEach(function (r) {
          host.appendChild(feedRow(r.latest_run, r.repo, now));
          anyRows = true;
          var failing = (r.workflow_rollup && r.workflow_rollup.failing_workflows) || [];
          failing.forEach(function (name) {
            if (r.latest_run && r.latest_run.workflowName === name && r.latest_run.conclusion === 'failure') {
              return;
            }
            host.appendChild(feedRow({
              workflowName: name,
              conclusion: 'failure',
              status: 'completed',
              updatedAt: (r.latest_run && r.latest_run.updatedAt) || ''
            }, r.repo, now));
          });
        });
      });
    }
    if (!anyRows) {
      var gh = estate.collectors && estate.collectors.github;
      var reason = gh && gh.reason ? gh.reason : 'no CI runs observed across vertical repos';
      var ref = gh ? gh.evidence_ref : null;
      host.appendChild(errBlock('NO GOVERNANCE SIGNAL', reason, ref));
    }

    if (gates) {
      var gl = document.createElement('div');
      gl.className = 'gate-line';
      var lbl = document.createElement('span');
      lbl.className = 'chip chip-gray';
      lbl.textContent = 'GATES';
      gl.appendChild(lbl);
      gates.forEach(function (g) {
        var c = document.createElement('span');
        var cls = g.state === 'PASS' ? 'chip-green' : g.state === 'FAIL' ? 'chip-red' : 'chip-amber';
        c.className = 'chip ' + cls;
        c.textContent = g.check;
        c.title = g.detail;
        gl.appendChild(c);
      });
      host.appendChild(gl);
    }
  }

  /* ---------- domains ---------- */

  function fact(label, value) {
    var s = document.createElement('span');
    s.appendChild(text(label + ' '));
    var b = document.createElement('b');
    b.textContent = value;
    s.appendChild(b);
    return s;
  }

  function renderDomains(estate) {
    var host = el('domains');
    clear(host);
    var dns = estate.collectors && estate.collectors.dns;
    var cf = estate.collectors && estate.collectors.cloudflare;

    var names = ['a-11-oy.com', 'a11oy.net'];
    var dnsZones = dns && dns.value ? dns.value : {};
    var cfZones = cf && cf.value ? cf.value : {};

    names.forEach(function (name) {
      var row = document.createElement('div');
      row.className = 'dom-row';
      row.setAttribute('data-testid', 'row-domain-' + name);

      var c1 = document.createElement('div');
      c1.className = 'dom-col';
      var nm = document.createElement('span');
      nm.className = 'dom-name';
      nm.textContent = name;
      c1.appendChild(nm);
      var facts = document.createElement('div');
      facts.className = 'dom-facts';
      c1.appendChild(facts);
      row.appendChild(c1);

      var c2 = document.createElement('div');
      c2.className = 'dom-col';
      var chips = document.createElement('div');
      chips.className = 'dom-facts';
      c2.appendChild(chips);
      row.appendChild(c2);

      var d = dnsZones[name];
      var reasons = [];
      if (d && d.truth_state !== 'UNAVAILABLE' && d.value) {
        facts.appendChild(fact('DNSSEC', d.value.dnssec));
        facts.appendChild(fact('NS', d.value.ns_records.length));
        var cc = document.createElement('span');
        cc.className = 'chip ' + (d.value.dnssec === 'SECURE' ? 'chip-green' : 'chip-amber') + ' mono';
        cc.textContent = d.value.dnssec;
        chips.appendChild(cc);
        if (d.reason) reasons.push('dig: ' + d.reason);
      } else {
        const cc2 = chip('UNAVAILABLE');
        chips.appendChild(cc2);
        reasons.push('dig: ' + (d && d.reason ? d.reason : 'no data'));
      }

      var z = cfZones[name];
      var cfFacts = document.createElement('div');
      cfFacts.className = 'dom-facts';
      c1.appendChild(cfFacts);
      var cfChip = document.createElement('span');
      if (z && z.truth_state === 'VERIFIED' && z.value) {
        cfFacts.appendChild(fact('REC', z.value.record_count));
        cfFacts.appendChild(fact('PROXIED', z.value.proxied_count));
        cfChip.className = 'chip chip-green mono';
        cfChip.textContent = 'CF ' + String(z.value.dnssec_status || 'active').toUpperCase();
      } else {
        cfChip.className = 'chip chip-gray mono';
        cfChip.textContent = 'CF UNAVAILABLE';
        reasons.push('cloudflare: ' + (z && z.reason ? z.reason : cf && cf.reason ? cf.reason : 'no data'));
        if (!cf || cf.truth_state === 'UNAVAILABLE') {
          /* z absent entirely because whole collector failed */
        }
      }
      chips.appendChild(cfChip);

      if (reasons.length) {
        var note = document.createElement('p');
        note.className = 'dom-note';
        note.textContent = reasons.join(' · ');
        row.appendChild(note);
        note.style.gridColumn = '1 / -1';
      }
      host.appendChild(row);
    });
  }

  /* ---------- receipts ---------- */

  function metaRow(k, v) {
    var r = document.createElement('div');
    r.className = 'meta-row';
    var kk = document.createElement('span');
    kk.className = 'k';
    kk.textContent = k;
    var vv = document.createElement('span');
    vv.className = 'v';
    vv.textContent = v == null || v === '' ? '—' : String(v);
    vv.title = vv.textContent;
    r.appendChild(kk);
    r.appendChild(vv);
    return r;
  }

  function renderReceipts(estate) {
    var host = el('receipts');
    clear(host);
    var rc = estate.collectors && estate.collectors.receipts;

    var verdict = null;
    var checks = [];
    var facts = null;

    if (rc && rc.value) {
      if (rc.value.verification && rc.value.verification.truth_state === 'VERIFIED' && rc.value.verification.value) {
        verdict = rc.value.verification.value.verdict;
        checks = rc.value.verification.value.checks || [];
      }
      if (rc.value.bundle && rc.value.bundle.truth_state === 'VERIFIED') {
        facts = rc.value.bundle.value;
      }
    }

    /* verdict block */
    var vb = document.createElement('div');
    vb.className = 'rc rc-verdict';
    var lbl = document.createElement('span');
    lbl.className = 'rc-label';
    lbl.textContent = 'SELF-AUDIT VERDICT';
    vb.appendChild(lbl);
    if (verdict) {
      var big = document.createElement('span');
      big.className = 'big-verdict verdict-' + verdict.toLowerCase();
      big.textContent = verdict;
      big.setAttribute('data-testid', 'text-audit-verdict');
      vb.appendChild(big);
    } else {
      vb.appendChild(chip((rc && rc.truth_state) || 'UNAVAILABLE'));
      var why = document.createElement('p');
      why.className = 'dom-note';
      why.textContent = rc && rc.reason ? rc.reason : 'verifier did not run';
      vb.appendChild(why);
    }
    host.appendChild(vb);

    /* facts block */
    var fb = document.createElement('div');
    fb.className = 'rc';
    var fl = document.createElement('span');
    fl.className = 'rc-label';
    fl.textContent = 'szl.dev/GovernedActionBundle/v1';
    fb.appendChild(fl);
    var mt = document.createElement('div');
    mt.className = 'meta-table';
    if (facts) {
      mt.appendChild(metaRow('receipt_id', facts.receipt_id));
      mt.appendChild(metaRow('action', facts.action_type));
      mt.appendChild(metaRow('decision', facts.decision + ' / ' + facts.side_effect_class));
      mt.appendChild(metaRow('completeness', facts.completeness || 'INCOMPLETE'));
      mt.appendChild(metaRow('retention', facts.retention_days != null ? facts.retention_days + ' days' : null));
      mt.appendChild(metaRow('issued_at', facts.created_at));
    } else {
      mt.appendChild(metaRow('bundle', rc && rc.value && rc.value.bundle ? rc.value.bundle.reason : 'UNAVAILABLE'));
    }
    var master = rc && rc.value ? rc.value.master_demo_state : null;
    mt.appendChild(
      metaRow(
        'master demo state',
        master && master.truth_state === 'VERIFIED' ? master.value.count + ' file(s)' : (master && master.reason) || 'UNAVAILABLE'
      )
    );
    fb.appendChild(mt);
    host.appendChild(fb);

    /* verifier checks */
    var cb = document.createElement('div');
    cb.className = 'rc';
    var cl = document.createElement('span');
    cl.className = 'rc-label';
    cl.textContent = 'VERIFIER CHECKS — EXECUTED LIVE';
    cb.appendChild(cl);
    var ck = document.createElement('div');
    ck.className = 'checks';
    if (checks.length) {
      checks.forEach(function (g) {
        var row = document.createElement('div');
        row.className = 'check';
        var st = document.createElement('span');
        st.className =
          'c-state ' +
          (g.state === 'PASS' ? 'c-pass' : g.state === 'FAIL' ? 'c-fail' : 'c-incomplete');
        st.textContent = g.state;
        var nm = document.createElement('span');
        nm.className = 'c-name';
        nm.textContent = g.check;
        var dt = document.createElement('span');
        dt.className = 'c-detail';
        dt.textContent = g.detail || '';
        row.appendChild(st);
        row.appendChild(nm);
        row.appendChild(dt);
        ck.appendChild(row);
      });
    } else {
      ck.appendChild(text('no checks executed — verifier unavailable'));
    }
    cb.appendChild(ck);
    host.appendChild(cb);

    /* the demo line */
    var demo = document.createElement('p');
    demo.className = 'rc rc-demo';
    if (verdict === 'INCOMPLETE') {
      demo.appendChild(text('Missing evidence ⇒ '));
      var b = document.createElement('b');
      b.textContent = 'INCOMPLETE';
      demo.appendChild(b);
      demo.appendChild(
        text(', never PASS — Law 4, enforced in the verifier, not in prose. That is the demo.')
      );
    } else if (verdict) {
      demo.appendChild(text('Verifier verdict ' + verdict + ' — signature is not truth; the evidence ledger decides.'));
    } else {
      demo.appendChild(text('Receipts collector UNAVAILABLE — the panel reports its evidence gap rather than rendering blank.'));
    }
    host.appendChild(demo);
  }

  /* ---------- fetch / orchestrate ---------- */

  // Optional deploy-preview rewrite to a proxy URL. Unmodified source uses the
  // same origin on every port, including HTTPS reverse proxies.
  function apiBase() {
    var configured = "__PORT_8000__";
    return configured.indexOf("__PORT_") === 0 ? "" : configured;
  }

  function fetchJson(path) {
    return fetch(apiBase() + path, { headers: { Accept: 'application/json' }, cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function isRecord(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function isTruthState(value) {
    return value === 'VERIFIED' || value === 'UNKNOWN' || value === 'UNAVAILABLE';
  }

  // Check the envelope required by the renderer before accepting an observation.
  // This does not attest the provider's claims or replace collector validation.
  function validEstate(value) {
    if (!isRecord(value) || !isRecord(value.summary) || !isRecord(value.collectors)) return false;
    var sum = value.summary;
    return isTruthState(sum.estate_state) &&
      Number.isInteger(sum.panels_total) && sum.panels_total >= 0 &&
      Number.isInteger(sum.panels_verified) && sum.panels_verified >= 0 &&
      sum.panels_verified <= sum.panels_total &&
      ['github', 'dns', 'cloudflare', 'receipts'].every(function (name) {
        var env = value.collectors[name];
        return isRecord(env) && isTruthState(env.truth_state);
      });
  }

  function validVerticals(value) {
    return isRecord(value) && Array.isArray(value.verticals) &&
      value.verticals.every(function (vertical) {
        return isRecord(vertical) && isTruthState(vertical.truth_state);
      });
  }

  function setPoll(state, detail) {
    var c = el('poll-state');
    var repl = chip(state);
    repl.id = 'poll-state';
    repl.setAttribute('data-testid', 'status-poll');
    if (detail) repl.title = detail;
    c.replaceWith(repl);
  }

  function renderSnapshotNotice() {
    var notice = el('snapshot-notice');
    var historical = [];
    [[lastEstate, 'estate'], [lastVerticals, 'verticals']].forEach(function (entry) {
      var snap = entry[0] && entry[0]._historical_snapshot;
      if (snap) historical.push(entry[1] + ': ' + (snap.generated_at || 'date unavailable'));
    });
    notice.hidden = historical.length === 0;
    notice.textContent = historical.length
      ? 'Live collection is degraded. Historical snapshots (' + historical.join('; ') +
        ') are available in the API response and are not used for current status.'
      : '';
  }

  function renderUnavailablePanel(id, endpoint, reason) {
    var host = el(id);
    clear(host);
    host.appendChild(errBlock('CURRENT OBSERVATION UNAVAILABLE', reason, endpoint));
    var replacement = chip('UNAVAILABLE');
    replacement.id = 'chip-' + id;
    el(replacement.id).replaceWith(replacement);
    setFoot('foot-' + id, { evidence_ref: endpoint, reason: reason });
  }

  function renderOntologyUnavailable(reason) {
    var host = el('ontology-graph');
    clear(host);
    host.appendChild(errBlock('NO ADMITTED GRAPH', reason, null));
    var badge = el('ontology-chip');
    badge.replaceWith(Object.assign(chip('UNAVAILABLE'), { id: 'ontology-chip' }));
    el('ontology-foot').textContent = 'READ ONLY · no actions · evidence not current';
  }

  var sourceNames = ['github', 'huggingface', 'cloudflare', 'dns', 'receipts'];
  var releaseStageDefinitions = [
    ['github_source', ['github'], 'IMMUTABLE_SOURCE_CHECKS_AND_REVIEW', 'GitHub source'],
    ['hf_catalog', ['huggingface'], 'PINNED_MODEL_AND_DATASET_ARTIFACT_BYTES', 'Hugging Face artifacts'],
    ['cloudflare_edge', ['cloudflare', 'dns'], 'EXACT_DEPLOYMENT_AND_RULE_READBACK', 'Cloudflare / DNS'],
    ['receipt_index', ['receipts'], 'INDEPENDENTLY_VERIFIED_RECEIPT_AUTHORITY', 'Receipt evidence'],
    ['model_evaluation', [], 'WEIGHT_BOUND_MEASUREMENTS_AND_BASELINES', 'Model evaluation'],
    ['runtime_deployment', [], 'SOURCE_MATCHED_EXTERNAL_RUNTIME_AND_AUTH', 'Runtime deployment'],
    ['payment_settlement', [], 'FACILITATOR_CHAIN_AND_PAYOUT_RECONCILIATION', 'x402 settlement'],
    ['pypi_distribution', [], 'PEP740_WHEEL_SDIST_TAG_AND_SOURCE_MATCH', 'PyPI release']
  ];
  var releaseEdgeDefinitions = [
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

  function validReleaseFabric(fabric, snapshotSha, nodes) {
    if (!isRecord(fabric) || fabric.schema !== 'szl.readonly.release_fabric.v1' ||
        fabric.scope !== 'SOURCE_COVERAGE_AND_RELEASE_REQUIREMENTS_ONLY' ||
        fabric.basis_source_snapshot_sha256 !== snapshotSha ||
        fabric.authority !== 'READ_ONLY_NO_APPROVAL' ||
        fabric.production_qualified !== false || fabric.can_deploy !== false ||
        fabric.financial_revenue_verified !== false ||
        fabric.fingerprint_is_signature !== false ||
        fabric.independently_qualified_stages !== 0 ||
        fabric.stage_count !== releaseStageDefinitions.length ||
        fabric.unverified_dependency_count !== releaseEdgeDefinitions.length ||
        !Array.isArray(fabric.stages) ||
        fabric.stages.length !== releaseStageDefinitions.length ||
        !Array.isArray(fabric.dependencies) ||
        fabric.dependencies.length !== releaseEdgeDefinitions.length ||
        typeof fabric.content_sha256 !== 'string' ||
        !/^[0-9a-f]{64}$/.test(fabric.content_sha256)) return false;

    var values = Object.create(null);
    nodes.forEach(function (n) {
      if (n.kind === 'evidence_source') values[n.label] = n.truth_state;
    });
    var admitted = 0;
    for (var i = 0; i < releaseStageDefinitions.length; i++) {
      var definition = releaseStageDefinitions[i];
      var stage = fabric.stages[i];
      var required = definition[1];
      if (!isRecord(stage) || stage.id !== definition[0] ||
          stage.kind !== 'release_stage' || stage.required_gate !== definition[2] ||
          stage.qualification !== 'NOT_ESTABLISHED' ||
          stage.can_execute_actions !== false ||
          !Array.isArray(stage.collectors) ||
          stage.collectors.length !== required.length ||
          !required.every(function (name, idx) { return stage.collectors[idx] === name; }) ||
          stage.collector_scope !== (required.length ? 'EXISTING_METADATA_ONLY' : 'NO_ADMITTED_COLLECTOR')) return false;
      var states = required.map(function (name) { return values[name] || 'UNAVAILABLE'; });
      var expected = !states.length || states.every(function (x) { return x === 'UNAVAILABLE'; })
        ? 'UNAVAILABLE'
        : states.every(function (x) { return x === 'VERIFIED'; }) ? 'VERIFIED' : 'UNKNOWN';
      if (stage.collector_state !== expected) return false;
      if (expected === 'VERIFIED') admitted++;
    }
    if (fabric.collector_verified_stages !== admitted) return false;
    for (var j = 0; j < releaseEdgeDefinitions.length; j++) {
      var edge = fabric.dependencies[j];
      var rule = releaseEdgeDefinitions[j];
      if (!isRecord(edge) || edge.source !== rule[0] || edge.target !== rule[1] ||
          edge.required_binding !== rule[2] ||
          edge.evidence_state !== 'NOT_ESTABLISHED' || edge.action_authorized !== false) return false;
    }
    return true;
  }

  function validReleaseImpact(result, basis, fabricSha, source) {
    if (!isRecord(result) || result.schema !== 'szl.readonly.release_impact.v1' ||
        result.mode !== 'HYPOTHETICAL_EVIDENCE_WITHDRAWAL' ||
        result.selected_source !== source || result.basis_source_snapshot_sha256 !== basis ||
        result.basis_release_fabric_sha256 !== fabricSha ||
        result.required_proof_state !== 'NOT_ESTABLISHED' ||
        result.production_qualified !== false || result.can_deploy !== false ||
        result.action_authorized !== false || result.source_modified !== false ||
        result.provider_state_changed !== false || result.model_quality_verified !== false ||
        result.settlement_verified !== false || result.fingerprint_is_signature !== false ||
        typeof result.content_sha256 !== 'string' ||
        !/^[0-9a-f]{64}$/.test(result.content_sha256) ||
        !Array.isArray(result.structurally_exposed_stages) ||
        !Array.isArray(result.structurally_exposed_edges) ||
        !Array.isArray(result.collector_stage_changes) ||
        result.structurally_exposed_stages.length > releaseStageDefinitions.length ||
        result.structurally_exposed_edges.length > releaseEdgeDefinitions.length ||
        result.collector_stage_changes.length > releaseStageDefinitions.length ||
        result.exposed_stage_count !== result.structurally_exposed_stages.length ||
        result.collector_changes_count !== result.collector_stage_changes.length ||
        ['VERIFIED', 'UNKNOWN', 'UNAVAILABLE'].indexOf(result.source_observation_before) < 0 ||
        result.source_observation_assumed_after !== 'UNAVAILABLE') return false;
    var seen = Object.create(null);
    for (var i = 0; i < result.structurally_exposed_stages.length; i++) {
      var stage = result.structurally_exposed_stages[i];
      if (!releaseStageDefinitions.some(function (x) { return x[0] === stage; }) ||
          seen[stage]) return false;
      seen[stage] = true;
    }
    for (var j = 0; j < result.collector_stage_changes.length; j++) {
      var change = result.collector_stage_changes[j];
      if (!isRecord(change) || !seen[change.stage] ||
          ['VERIFIED', 'UNKNOWN', 'UNAVAILABLE'].indexOf(change.before) < 0 ||
          ['UNKNOWN', 'UNAVAILABLE'].indexOf(change.after) < 0 ||
          change.before === change.after) return false;
    }
    for (var k = 0; k < result.structurally_exposed_edges.length; k++) {
      var edge = result.structurally_exposed_edges[k];
      if (!isRecord(edge) || edge.binding_verified !== false ||
          !seen[edge.source] || !seen[edge.target] ||
          !releaseEdgeDefinitions.some(function (x) {
            return x[0] === edge.source && x[1] === edge.target &&
              x[2] === edge.required_binding;
          })) return false;
    }
    return true;
  }

  function renderReleaseFabric(fabric, host, basisSha) {
    var wrap = document.createElement('section');
    wrap.className = 'release-fabric';
    wrap.setAttribute('aria-label', 'Cross-platform release proof dependencies');
    var heading = document.createElement('h3');
    heading.textContent = 'ONE RELEASE CHAIN · EIGHT EVIDENCE GATES';
    wrap.appendChild(heading);
    var boundary = document.createElement('p');
    boundary.className = 'mono release-fabric-boundary';
    boundary.textContent = '0/8 independently qualified · 0/9 links proven · no deployment, payment, or release authority';
    wrap.appendChild(boundary);
    var cards = document.createElement('ol');
    cards.className = 'release-fabric-stages';
    releaseStageDefinitions.forEach(function (definition, i) {
      var stage = fabric.stages[i];
      var item = document.createElement('li');
      item.className = 'release-fabric-stage';
      var label = document.createElement('strong');
      label.textContent = definition[3];
      item.appendChild(label);
      var state = document.createElement('span');
      state.className = 'mono';
      state.textContent = 'Collector metadata: ' + stage.collector_state;
      item.appendChild(state);
      var admission = document.createElement('span');
      admission.className = 'mono release-fabric-held';
      admission.textContent = 'GATE NOT ESTABLISHED';
      item.appendChild(admission);
      var gate = document.createElement('code');
      gate.textContent = definition[2];
      item.appendChild(gate);
      cards.appendChild(item);
    });
    wrap.appendChild(cards);
    var edgesHeading = document.createElement('h4');
    edgesHeading.textContent = 'Required source-to-outcome bindings';
    wrap.appendChild(edgesHeading);
    var edges = document.createElement('ul');
    edges.className = 'release-fabric-edges';
    releaseEdgeDefinitions.forEach(function (rule) {
      var item = document.createElement('li');
      var from = releaseStageDefinitions.find(function (s) { return s[0] === rule[0]; });
      var to = releaseStageDefinitions.find(function (s) { return s[0] === rule[1]; });
      var label = document.createElement('strong');
      label.textContent = from[3] + ' → ' + to[3];
      item.appendChild(label);
      var proof = document.createElement('code');
      proof.textContent = rule[2] + ' · NOT ESTABLISHED';
      item.appendChild(proof);
      edges.appendChild(item);
    });
    wrap.appendChild(edges);
    // On-demand rehearsal only. No poll, controller, entitlement, model call or
    // new provider read. The basis is the same WebCrypto-checked ontology.
    var impactForm = document.createElement('div');
    impactForm.className = 'release-impact';
    impactForm.setAttribute('aria-label', 'Counterfactual loss of evidence');
    var impactTitle = document.createElement('h4');
    impactTitle.textContent = 'WHAT LOSES SUPPORT? · REHEARSAL ONLY';
    impactForm.appendChild(impactTitle);
    var impactLabel = document.createElement('label');
    impactLabel.textContent = 'Withhold evidence source';
    var impactSelect = document.createElement('select');
    impactSelect.setAttribute('aria-label', 'Evidence source to withhold');
    sourceNames.forEach(function (name) {
      var option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      impactSelect.appendChild(option);
    });
    impactSelect.value = 'github';
    impactLabel.appendChild(impactSelect);
    impactForm.appendChild(impactLabel);
    var impactButton = document.createElement('button');
    impactButton.type = 'button';
    impactButton.textContent = 'Rehearse loss';
    impactForm.appendChild(impactButton);
    var impactResult = document.createElement('p');
    impactResult.className = 'mono release-impact-result';
    impactResult.setAttribute('role', 'status');
    impactResult.setAttribute('aria-live', 'polite');
    impactResult.textContent = 'NOT RUN · source bytes and authority unchanged';
    impactForm.appendChild(impactResult);
    impactButton.onclick = async function () {
      var selected = impactSelect.value;
      if (sourceNames.indexOf(selected) < 0) {
        impactResult.textContent = 'UNAVAILABLE · SOURCE_NOT_ALLOWED';
        return;
      }
      var startEpoch = refreshEpoch;
      impactButton.disabled = true;
      impactResult.textContent = 'OBSERVING · read-only counterfactual';
      try {
        var endpoint = apiBase() + '/api/release-impact?source=' +
          encodeURIComponent(selected) + '&basis=' + encodeURIComponent(basisSha);
        var response = await fetch(endpoint, {
          headers: { Accept: 'application/json' }, cache: 'no-store',
        });
        if (startEpoch !== refreshEpoch) return;
        if (!response.ok) {
          impactResult.textContent = response.status === 409
            ? 'UNAVAILABLE · SOURCE_SNAPSHOT_CHANGED (refresh first)'
            : 'UNAVAILABLE · rehearsal unavailable, no fallback';
          return;
        }
        var result = await response.json();
        if (!validReleaseImpact(result, basisSha, fabric.content_sha256, selected)) {
          impactResult.textContent = 'UNAVAILABLE · IMPACT_CONTRACT_INVALID';
          return;
        }
        var body = Object.assign({}, result);
        delete body.content_sha256;
        if (await graphSha256(body) !== result.content_sha256) {
          impactResult.textContent = 'UNAVAILABLE · IMPACT_CHECKSUM_INVALID';
          return;
        }
        if (startEpoch !== refreshEpoch) return;
        var labels = result.structurally_exposed_stages.map(function (id) {
          var item = releaseStageDefinitions.find(function (d) { return d[0] === id; });
          return item[3];
        });
        impactResult.textContent = 'REHEARSAL: ' + selected + ' evidence withheld · ' +
          result.collector_changes_count + ' metadata stages change · ' +
          result.exposed_stage_count + ' structurally exposed: ' + labels.join(' → ') +
          '. All links remain unproved. No actions, deployment or revenue authorized.';
      } catch (error) {
        if (startEpoch === refreshEpoch) {
          impactResult.textContent = 'UNAVAILABLE · readback or checksum failure';
        }
      } finally {
        impactButton.disabled = false;
      }
    };
    wrap.appendChild(impactForm);
    var note = document.createElement('p');
    note.className = 'mono release-fabric-foot';
    note.textContent = 'RECOMPUTED UNSIGNED GRAPH SHA-256 ' + fabric.content_sha256.slice(0, 24) +
      '… · collector success does not imply verified weights, settled payments, or a published wheel';
    wrap.appendChild(note);
    host.appendChild(wrap);
  }

  function validOntology(payload) {
    if (!isRecord(payload) || payload.schema !== 'szl.readonly.evidence_graph.v1' ||
        !isRecord(payload.authorization) || payload.authorization.mode !== 'READ_ONLY' ||
        payload.authorization.can_execute_actions !== false ||
        !isRecord(payload.provenance) || payload.provenance.snapshot_signature !== 'NOT_ESTABLISHED' ||
        !Array.isArray(payload.nodes) || payload.nodes.length !== 6 ||
        !Array.isArray(payload.links) || payload.links.length !== 5 ||
        typeof payload.content_sha256 !== 'string' ||
        !/^[0-9a-f]{64}$/.test(payload.content_sha256) ||
        typeof payload.source_generated_at !== 'string' || !payload.source_generated_at ||
        typeof payload.source_snapshot_sha256 !== 'string' ||
        !/^[0-9a-f]{64}$/.test(payload.source_snapshot_sha256) ||
        !Number.isInteger(payload.total_sources) || payload.total_sources !== 5 ||
        !Number.isInteger(payload.verified_sources) || payload.verified_sources < 0 ||
        payload.verified_sources > 5 || !isTruthState(payload.rollup)) return false;
    var names = new Set();
    var actual = 0;
    for (var i = 0; i < payload.nodes.length; i++) {
      var node = payload.nodes[i];
      if (!isRecord(node) || node.action_authorized !== false) return false;
      if (i === 0) {
        if (node.id !== 'snapshot:estate' || node.kind !== 'snapshot') return false;
        continue;
      }
      if (node.kind !== 'evidence_source' || typeof node.label !== 'string' ||
          !sourceNames.includes(node.label) || node.id !== 'source:' + node.label ||
          names.has(node.label) || !isTruthState(node.truth_state) ||
          typeof node.reason_code !== 'string' || node.reason_code.length > 80) return false;
      names.add(node.label);
      if (node.truth_state === 'VERIFIED') actual++;
    }
    if (names.size !== 5 || actual !== payload.verified_sources) return false;
    var states = payload.nodes.slice(1).map(function (n) { return n.truth_state; });
    var expected = states.every(function (state) { return state === 'VERIFIED'; }) ? 'VERIFIED' :
      states.every(function (state) { return state === 'UNAVAILABLE'; }) ? 'UNAVAILABLE' : 'UNKNOWN';
    if (expected !== payload.rollup) return false;
    var links = new Set();
    for (var j = 0; j < payload.links.length; j++) {
      var edge = payload.links[j];
      if (!isRecord(edge) || edge.kind !== 'observed_in' ||
          edge.target !== 'snapshot:estate' ||
          !sourceNames.some(function (n) { return edge.source === 'source:' + n; }) ||
          links.has(edge.source)) return false;
      links.add(edge.source);
    }
    return links.size === 5 && validReleaseFabric(payload.release_fabric, payload.source_snapshot_sha256, payload.nodes);
  }

  /* Recompute all three JSON integrity digests before trusting the display.
     Server hashes use Python json.dumps(sort_keys=True,separators=(',', ':'),
     ensure_ascii=True). All admitted graph numbers are bounded integers.
     A matching checksum is data consistency, NEVER source authenticity. */
  function asciiJsonString(value) {
    return JSON.stringify(value).replace(/[\u007f-\uffff]/g, function (character) {
      return '\\u' + character.charCodeAt(0).toString(16).padStart(4, '0');
    });
  }

  function canonicalGraphJson(value, depth) {
    if (depth > 24) throw new Error('GRAPH_DEPTH_LIMIT');
    if (value === null) return 'null';
    if (typeof value === 'string') return asciiJsonString(value);
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number' && Number.isSafeInteger(value)) return String(value);
    if (Array.isArray(value) && value.length <= 100) {
      return '[' + value.map(function (item) {
        return canonicalGraphJson(item, depth + 1);
      }).join(',') + ']';
    }
    if (isRecord(value)) {
      var keys = Object.keys(value);
      if (keys.length > 100) throw new Error('GRAPH_KEY_LIMIT');
      return '{' + keys.sort().map(function (key) {
        return asciiJsonString(key) + ':' + canonicalGraphJson(value[key], depth + 1);
      }).join(',') + '}';
    }
    throw new Error('GRAPH_UNSUPPORTED_TYPE');
  }

  async function graphSha256(value) {
    if (typeof crypto === 'undefined' || !crypto.subtle ||
        typeof crypto.subtle.digest !== 'function' ||
        typeof TextEncoder === 'undefined') throw new Error('WEBCRYPTO_UNAVAILABLE');
    var content = canonicalGraphJson(value, 0);
    if (content.length > 65536) throw new Error('GRAPH_BYTE_LIMIT');
    var bytes = new TextEncoder().encode(content);
    var digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest)).map(function (byte) {
      return byte.toString(16).padStart(2, '0');
    }).join('');
  }

  async function verifiedGraphChecksums(payload) {
    try {
      if (!validOntology(payload)) return false;
      var sourceBody = {
        source_generated_at: payload.source_generated_at,
        observations: payload.nodes.slice(1).map(function (node) {
          return [node.id, node.truth_state, node.observed_at,
            node.evidence_ref_sha256];
        })
      };
      if (await graphSha256(sourceBody) !== payload.source_snapshot_sha256) {
        return false;
      }
      var fabricBody = Object.assign({}, payload.release_fabric);
      delete fabricBody.content_sha256;
      if (await graphSha256(fabricBody) !== payload.release_fabric.content_sha256) {
        return false;
      }
      var outerBody = Object.assign({}, payload);
      delete outerBody.content_sha256;
      if (await graphSha256(outerBody) !== payload.content_sha256) {
        return false;
      }
      return true;
    } catch (error) {
      // No alternative unchecked path on unsupported WebCrypto, malformed
      // graph data, oversized payload or hash mismatch.
      return false;
    }
  }

  function renderOntology(payload) {
    var host = el('ontology-graph');
    clear(host);
    var badge = el('ontology-chip');
    if (!validOntology(payload)) {
      renderOntologyUnavailable('INVALID_GRAPH_CONTRACT');
      return;
    }
    var replacement = chip(payload.rollup);
    replacement.id = 'ontology-chip';
    badge.replaceWith(replacement);
    var list = document.createElement('ul');
    list.className = 'ontology-sources';
    payload.nodes.filter(function (node) { return node.kind === 'evidence_source'; }).forEach(function (node) {
      var item = document.createElement('li');
      item.className = 'ontology-source';
      var marker = document.createElement('span');
      marker.className = 'ontology-marker ontology-marker-' + (THEME[node.truth_state] ? node.truth_state : 'UNAVAILABLE');
      marker.setAttribute('aria-hidden', 'true');
      var label = document.createElement('strong');
      label.textContent = node.label;
      var state = document.createElement('span');
      state.textContent = node.truth_state + ' · ' + node.reason_code;
      state.className = 'mono';
      item.appendChild(marker);
      item.appendChild(label);
      item.appendChild(state);
      list.appendChild(item);
    });
    host.appendChild(list);
    renderReleaseFabric(payload.release_fabric, host, payload.source_snapshot_sha256);
    el('ontology-foot').textContent =
      'READ ONLY · three independent SHA-256 consistency checks passed · source ' +
      payload.source_snapshot_sha256.slice(0, 16) +
      ' · source authenticity: NOT ESTABLISHED · actions: DENIED';
  }

  var refreshEpoch = 0;
  function refresh() {
    var epoch = ++refreshEpoch;
    var estateSnapshot = null;
    var verticalSnapshot = null;
    var results = { estate: false, verticals: false, ontology: false };
    var graph = null;
    var errors = {};
    var estateP = fetchJson('/api/estate').then(function (d) {
      if (!validEstate(d)) throw new Error('Invalid estate response');
      estateSnapshot = d;
      results.estate = true;
    }).catch(function (e) {
      estateSnapshot = null;
      errors.estate = String(e);
    });
    var vertP = fetchJson('/api/verticals').then(function (d) {
      if (!validVerticals(d)) throw new Error('Invalid verticals response');
      verticalSnapshot = d;
      results.verticals = true;
    }).catch(function (e) {
      verticalSnapshot = null;
      errors.verticals = String(e);
    });

    var graphDisabled = false;
    var graphIntegrityFailure = false;
    var graphP = fetch(apiBase() + '/api/ontology', {
      headers: { Accept: 'application/json' }, cache: 'no-store',
    }).then(function (r) {
      if (r.status === 503) {
        return r.json().then(function (body) {
          if (body && body.reason_code === 'FEATURE_NOT_ADMITTED') {
            graphDisabled = true;
            return null;
          }
          throw new Error('Ontology HTTP 503');
        });
      }
      if (!r.ok) throw new Error('Ontology HTTP ' + r.status);
      return r.json();
    }).then(async function (d) {
      if (graphDisabled) return;
      if (!validOntology(d) || !await verifiedGraphChecksums(d)) {
        graphIntegrityFailure = true;
        throw new Error('GRAPH_CHECKSUM_UNVERIFIED');
      }
      graph = d;
      results.ontology = true;
    }).catch(function () {
      graph = null;
    });
    return Promise.allSettled([estateP, vertP, graphP]).then(function () {
      if (epoch !== refreshEpoch) return;
      lastEstate = estateSnapshot;
      lastVerticals = verticalSnapshot;
      var bound = Boolean(lastEstate && graph &&
        graph.source_generated_at === lastEstate.generated_at &&
        graph.authorization && graph.authorization.can_execute_actions === false);
      if (bound) {
        renderOntology(graph);
      } else {
        renderOntologyUnavailable(graph ? 'SOURCE_SNAPSHOT_MISMATCH' :
          graphIntegrityFailure ? 'GRAPH_CHECKSUM_UNVERIFIED' : 'FEATURE_NOT_ADMITTED_OR_UNAVAILABLE');
      }
      renderSnapshotNotice();
      if (lastEstate) {
        renderStrip(lastEstate, lastVerticals);
        renderFeed(lastEstate, lastVerticals);
        renderDomains(lastEstate);
        renderReceipts(lastEstate);
        setFoot('foot-feed', lastEstate.collectors ? lastEstate.collectors.github : null);
        setFoot('foot-domains', lastEstate.collectors ? lastEstate.collectors.cloudflare : null);
        setFoot('foot-receipts', lastEstate.collectors ? lastEstate.collectors.receipts : null);
      } else {
        ['feed', 'domains', 'receipts'].forEach(function (id) {
          renderUnavailablePanel(id, '/api/estate', errors.estate);
        });
        ['strip-ratio', 'strip-issues', 'strip-head', 'strip-refresh'].forEach(function (id) {
          el(id).textContent = '—';
        });
        el('ratio-fill').style.width = '0%';
        clear(el('strip-state'));
        el('strip-state').appendChild(chip('UNAVAILABLE'));
      }
      if (lastVerticals) {
        renderVerticals(lastVerticals);
        setFoot('foot-verticals', lastVerticals.issues_scan);
      } else {
        renderUnavailablePanel('verticals', '/api/verticals', errors.verticals);
      }
      renderPanelChips();
      if (results.estate || results.verticals || results.ontology) {
        var baseVerified = Boolean(results.estate && results.verticals &&
          lastEstate && lastEstate.summary && lastEstate.summary.estate_state === 'VERIFIED' &&
          lastVerticals && Array.isArray(lastVerticals.verticals) &&
          lastVerticals.verticals.length > 0 &&
          lastVerticals.verticals.every(function (v) { return v.truth_state === 'VERIFIED'; }));
        // An explicitly disabled optional graph does not demote an independently
        // qualified base dashboard. An unexpected graph failure or conflicting
        // graph observation MUST downgrade the overall poll status.
        var graphQualified = graphDisabled || Boolean(bound && graph && graph.rollup === 'VERIFIED');
        var estateVerified = baseVerified && graphQualified;
        setPoll(estateVerified ? 'VERIFIED' : 'UNKNOWN',
          estateVerified ? null : 'collection, binding or evidence incomplete');
      } else {
        setPoll('UNAVAILABLE', 'current observations unavailable');
      }
    });
  }

  function renderPanelChips() {
    if (lastEstate && lastEstate.collectors) {
      var c = lastEstate.collectors;
      var pairs = [
        ['chip-feed', c.github],
        ['chip-domains', null], // domains merges two collectors
        ['chip-receipts', c.receipts],
      ];
      pairs.forEach(function (p) {
        if (!p[1]) return;
        var target = el(p[0]);
        var repl = chip(p[1].truth_state);
        repl.id = p[0];
        if (p[1].reason) repl.title = p[1].reason;
        target.replaceWith(repl);
      });
      var dnsState = c.dns ? c.dns.truth_state : 'UNAVAILABLE';
      var cfState = c.cloudflare ? c.cloudflare.truth_state : 'UNAVAILABLE';
      var merged = dnsState === cfState ? dnsState : 'UNKNOWN';
      var dm = chip(merged);
      dm.id = 'chip-domains';
      dm.title = 'dig: ' + dnsState + ' · cloudflare: ' + cfState;
      el('chip-domains').replaceWith(dm);
    }
    if (lastVerticals) {
      var states = lastVerticals.verticals.map(function (v) { return v.truth_state; });
      var all = states.length === 0 ? 'UNKNOWN' : states.every(function (s) { return s === 'VERIFIED'; })
        ? 'VERIFIED'
        : states.every(function (s) { return s === 'UNAVAILABLE'; })
          ? 'UNAVAILABLE'
          : 'UNKNOWN';
      var repl = chip(all);
      repl.id = 'chip-verticals';
      el('chip-verticals').replaceWith(repl);
    }
    /* ensure ids survive replacement on first paint */
    ['chip-feed', 'chip-domains', 'chip-receipts', 'chip-verticals'].forEach(function (id) {
      var n = el(id);
      if (n) n.setAttribute('data-testid', 'status-' + id.replace('chip-', ''));
    });
  }

  /* ---------- clock ---------- */

  function tickClock() {
    var d = new Date();
    var p = function (n) { return String(n).padStart(2, '0'); };
    el('clock').textContent =
      d.getUTCFullYear() +
      '-' + p(d.getUTCMonth() + 1) +
      '-' + p(d.getUTCDate()) +
      ' ' + p(d.getUTCHours()) +
      ':' + p(d.getUTCMinutes()) +
      ':' + p(d.getUTCSeconds()) + ' UTC';
  }

  tickClock();
  setInterval(tickClock, 1000);
  refresh();
  setInterval(refresh, POLL_MS);
})();
