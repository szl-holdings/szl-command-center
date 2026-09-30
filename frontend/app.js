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
    left.appendChild(runDot(latest.conclusion, latest.status));
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
        lead.textContent = 'latest CI conclusions';
        hd.appendChild(lead);
        host.appendChild(hd);
        withRuns.forEach(function (r) {
          host.appendChild(feedRow(r.latest_run, r.repo, now));
          anyRows = true;
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

  function fetchJson(path) {
    return fetch(path, { headers: { Accept: 'application/json' }, cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
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

  function refresh() {
    var results = { estate: false, verticals: false };
    var estateP = fetchJson('/api/estate').then(function (d) {
      lastEstate = d;
      results.estate = true;
    }).catch(function (e) {
      lastEstate = null;
      el('strip-ratio').textContent = '—';
      setFoot('foot-feed', { evidence_ref: '/api/estate', reason: String(e) });
    });
    var vertP = fetchJson('/api/verticals').then(function (d) {
      lastVerticals = d;
      results.verticals = true;
    }).catch(function (e) {
      lastVerticals = null;
      setFoot('foot-verticals', { evidence_ref: '/api/verticals', reason: String(e) });
    });

    return Promise.allSettled([estateP, vertP]).then(function () {
      if (lastEstate) {
        renderStrip(lastEstate, lastVerticals);
        renderFeed(lastEstate, lastVerticals);
        renderDomains(lastEstate);
        renderReceipts(lastEstate);
        setFoot('foot-feed', lastEstate.collectors ? lastEstate.collectors.github : null);
        setFoot('foot-domains', lastEstate.collectors ? lastEstate.collectors.cloudflare : null);
        setFoot('foot-receipts', lastEstate.collectors ? lastEstate.collectors.receipts : null);
      }
      if (lastVerticals) {
        renderVerticals(lastVerticals);
        setFoot('foot-verticals', lastVerticals.issues_scan);
      }
      renderPanelChips();
      if (results.estate || results.verticals) {
        var partial = !(results.estate && results.verticals);
        setPoll(partial ? 'UNKNOWN' : 'VERIFIED', partial ? 'one endpoint unreachable' : null);
      } else {
        setPoll('UNAVAILABLE', 'backend unreachable — last known state retained');
        if (lastEstate) {
          renderStrip(lastEstate, lastVerticals);
          renderFeed(lastEstate, lastVerticals);
          renderDomains(lastEstate);
          renderReceipts(lastEstate);
        } else {
          ['feed', 'domains', 'receipts'].forEach(function (id) {
            var host = el(id);
            clear(host);
            host.appendChild(errBlock('BACKEND UNREACHABLE', 'no data has ever been observed — this panel refuses to render blank', '/api/estate'));
          });
          ['strip-ratio', 'strip-issues', 'strip-head'].forEach(function (id) {
            el(id).textContent = '—';
          });
        }
        if (lastVerticals) {
          renderVerticals(lastVerticals);
        } else {
          var vh = el('verticals');
          clear(vh);
          vh.appendChild(errBlock('BACKEND UNREACHABLE', 'no vertical data ever observed — reported, not blank', '/api/verticals'));
        }
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
      var all = states.every(function (s) { return s === 'VERIFIED'; })
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
