/* Studio client. Vanilla JS, no framework, no build step. Every value from the server is placed with textContent or
   setAttribute, never parsed as markup, so labels a user types cannot inject anything. All UI strings come from
   window.STUDIO_I18N (i18n.js). */
(function () {
  'use strict';
  var I18N = window.STUDIO_I18N;
  var STAGES = ['acquire', 'inspect', 'prepare', 'execute', 'reconcile', 'finalize'];
  var MARKETS = ['ksa', 'uae', 'egy', 'qat'];
  var HEX = /^#[0-9A-Fa-f]{6}$/;
  var SAFE_TOKEN = /^(#[0-9A-F]{6}|rgba\(\d{1,3},\d{1,3},\d{1,3},(0|1|0\.\d{1,4})\))$/;
  var ui = { lang: pref('studio.lang', 'en'), theme: pref('studio.theme', 'system'), tab: pref('studio.tab', 'compile'),
    kind: 'all', market: 'ksa', invLang: 'en', invoice: null, entity: null };
  var data = { state: null, compile: null, apply: null, theme: null, invoice: null, exp: null };
  var timers = {};
  var compileSeq = 0;

  function pref(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }
  function keep(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } }
  function $(id) { return document.getElementById(id); }
  function tIn(lang, key, vars) {
    var s = (I18N[lang] && I18N[lang][key]) || I18N.en[key];
    if (s === undefined) return key;
    Object.keys(vars || {}).forEach(function (k) { s = s.split('{' + k + '}').join(String(vars[k])); });
    return s;
  }
  function t(key, vars) { return tIn(ui.lang, key, vars); }
  function has(key) { return Object.prototype.hasOwnProperty.call(I18N.en, key); }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === undefined || v === null || v === false) return;
      if (k === 'text') e.textContent = String(v);
      else if (k === 'class') e.className = v;
      else if (k.indexOf('on') === 0) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : String(v));
    });
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined) e.append(c); });
    return e;
  }
  function loc(obj) { return obj ? (obj[ui.lang] || obj.en || obj.ar || '') : ''; }
  function fill(node) { node.replaceChildren.apply(node, [].slice.call(arguments, 1).filter(function (k) { return k !== null && k !== undefined; })); }
  function debounce(name, ms, fn) { clearTimeout(timers[name]); timers[name] = setTimeout(fn, ms); }
  function hint(code) { return has('code.' + code) ? t('code.' + code) : t('code.unknown'); }

  function api(method, path, body) {
    var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (method !== 'GET') opts.body = JSON.stringify(body || {});
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: { code: 'STUDIO-CLIENT-PARSE', path: '/' } }; })
        .then(function (d) { d.httpStatus = r.status; return d; });
    }).catch(function () { return { ok: false, error: { code: 'STUDIO-CLIENT-NETWORK', path: '/' }, httpStatus: 0 }; });
  }
  function showErr(id, res) {
    var box = $(id);
    if (!res || res.ok !== false || !res.error) { box.hidden = true; box.textContent = ''; return false; }
    box.hidden = false;
    box.replaceChildren(el('span', { text: hint(res.error.code) + ' ' }), el('span', { class: 'mono', text: res.error.code + ' ' + res.error.path, dir: 'ltr' }));
    return true;
  }

  /* ------------------------------------------------------------ chrome: language, theme, tabs */
  function applyChrome() {
    var root = document.documentElement;
    root.lang = ui.lang; root.dir = ui.lang === 'ar' ? 'rtl' : 'ltr';
    if (ui.theme === 'system') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', ui.theme);
    document.title = t('app.title');
    document.querySelectorAll('[data-i18n]').forEach(function (n) { n.textContent = t(n.getAttribute('data-i18n')); });
    $('langBtn').textContent = t('app.langToggle');
    $('themeBtn').textContent = t('app.theme.' + ui.theme);
    $('tabs').setAttribute('aria-label', t('panel.title'));
    $('kinds').setAttribute('aria-label', t('compile.filter'));
    $('qr').setAttribute('aria-label', t('inv.qrAlt'));
    document.querySelectorAll('#tabs [role=tab]').forEach(function (b) {
      var on = b.getAttribute('data-tab') === ui.tab;
      b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1;
      $('pane-' + b.getAttribute('data-tab')).hidden = !on;
    });
  }
  function rerender() {
    applyChrome();
    if (data.state) renderState();
    renderCompile(); renderApply(); renderTheme(); renderInvoice(); renderExport();
  }

  /* ------------------------------------------------------------ editor */
  function renderState() {
    var s = data.state, bp = s.blueprint;
    var badge = $('engineBadge');
    badge.textContent = t(s.engine.labelKey);
    badge.className = 'badge ' + (s.engine.kind === 'fake' ? 'warn' : 'neutral');
    [['legalEn', bp.legalName.en], ['legalAr', bp.legalName.ar], ['tradeEn', bp.tradeName.en], ['tradeAr', bp.tradeName.ar]]
      .forEach(function (p) { if (document.activeElement !== $(p[0])) $(p[0]).value = p[1]; });
    var groups = {};
    s.components.forEach(function (c) { var g = c.id.split('.')[0]; (groups[g] = groups[g] || []).push(c); });
    $('components').replaceChildren.apply($('components'), Object.keys(groups).map(function (g) {
      return el('div', { class: 'group' }, [el('h4', { text: has('group.' + g) ? t('group.' + g) : g })].concat(groups[g].map(componentRow)));
    }));
    var sel = $('entitySel');
    if (!ui.entity) ui.entity = bp.entities[0].id;
    sel.replaceChildren.apply(sel, bp.entities.map(function (e) {
      return el('option', { value: e.id, text: loc(e.labels) + ' (' + e.id + ')', selected: e.id === ui.entity });
    }));
    var ent = bp.entities.filter(function (e) { return e.id === ui.entity; })[0];
    if (ent) {
      if (document.activeElement !== $('entEn')) $('entEn').value = ent.labels.en;
      if (document.activeElement !== $('entAr')) $('entAr').value = ent.labels.ar;
    }
    var colour = bp.primaryColour || '';
    if (document.activeElement !== $('colorHex')) $('colorHex').value = colour;
    if (HEX.test(colour)) $('colorPick').value = colour.toLowerCase();
  }
  function componentRow(c) {
    var id = 'cmp-' + c.id.replace(/[^a-z0-9]/gi, '-');
    var box = el('input', { type: 'checkbox', id: id, role: 'switch', checked: c.enabled, 'aria-checked': String(c.enabled) });
    box.addEventListener('change', function () { toggleComponent(c, box.checked); });
    var req = null;
    if (c.requiredBy.length) {
      req = el('div', { class: 'req' + (c.enabled ? '' : ' break'),
        text: t(c.enabled ? 'cmp.requiredBy' : 'cmp.missingFor', { list: c.requiredBy.join(', ') }) });
    } else if (c.boundEntities.length) {
      req = el('div', { class: 'req' + (c.enabled ? '' : ' break'), text: t(c.enabled ? 'cmp.usedBy' : 'cmp.entitiesBroken', { n: c.boundEntities.length }) });
    }
    return el('div', { class: 'comp' }, [box,
      el('label', { for: id, class: 'name', text: loc(c.name) || c.id }),
      el('div', { class: 'meta' }, [el('span', { class: 'mono', text: c.id + ' ' + (c.version || ''), dir: 'ltr' }),
        el('span', { class: 'tag', text: t('level.' + c.level) }),
        c.touchesLedgerOrTax ? el('span', { class: 'tag', text: t('cmp.ledger') }) : null,
        el('span', { class: 'tag', text: c.eligible.sandbox ? t('cmp.eligible') : t('cmp.notEligible') })]),
      req]);
  }
  function afterEdit(res, errId) {
    if (showErr(errId, res)) return;
    data.state = res; renderState(); scheduleCompile();
  }
  function toggleComponent(c, on) {
    api('PUT', '/api/blueprint/components', { id: c.id, enabled: on }).then(function (r) { afterEdit(r, 'globalErr'); });
  }
  function saveCompany() {
    var body = { legalName: { en: $('legalEn').value, ar: $('legalAr').value }, tradeName: { en: $('tradeEn').value, ar: $('tradeAr').value } };
    api('PUT', '/api/blueprint/company', body).then(function (r) {
      ['legalEn', 'legalAr', 'tradeEn', 'tradeAr'].forEach(function (i) { $(i).removeAttribute('aria-invalid'); });
      if (r.ok === false && r.error) {
        var m = /^\/(legalName|tradeName)\/(ar|en)$/.exec(r.error.path);
        if (m) $((m[1] === 'legalName' ? 'legal' : 'trade') + (m[2] === 'ar' ? 'Ar' : 'En')).setAttribute('aria-invalid', 'true');
      }
      afterEdit(r, 'companyErr');
    });
  }
  function saveLabels() {
    var id = ui.entity;
    api('PUT', '/api/blueprint/entities/' + encodeURIComponent(id) + '/labels', { en: $('entEn').value, ar: $('entAr').value })
      .then(function (r) { afterEdit(r, 'labelErr'); });
  }
  function saveColour(value) {
    $('colorHex').removeAttribute('aria-invalid');
    api('PUT', '/api/blueprint/branding', { primaryColour: value }).then(function (r) {
      if (r.ok === false) $('colorHex').setAttribute('aria-invalid', 'true');
      afterEdit(r, 'brandErr');
      if (r.ok !== false) loadTheme();
    });
  }

  /* ------------------------------------------------------------ compile */
  function scheduleCompile() { debounce('compile', 300, runCompile); }
  function runCompile() {
    var seq = ++compileSeq;
    api('POST', '/api/compile').then(function (r) { if (seq === compileSeq) { data.compile = r; renderCompile(); } });
  }
  function renderCompile() {
    var r = data.compile, st = $('compileStatus');
    if (!r) { st.textContent = t('compile.running'); return; }
    if (r.ok) {
      st.className = 'status ok';
      fill(st, el('b', { text: t('compile.ok', { n: r.stepCount }) }), el('span', { class: 'mono', text: r.artifactId, dir: 'ltr' }),
        el('span', { class: 'hint', text: t('compile.summary', { pc: r.postConditionCount, impact: r.risk.maxImpact, env: r.environment }) }),
        r.risk.touchesLedgerOrTax ? el('span', { class: 'tag', text: t('compile.ledger') }) : null);
      $('refusals').replaceChildren();
    } else if (r.refusals) {
      st.className = 'status bad';
      st.replaceChildren(el('b', { text: t('compile.refused', { n: r.refusals.length }) }), el('span', { class: 'hint', text: t('compile.refusedNote') }));
      $('refusals').replaceChildren.apply($('refusals'), r.refusals.map(function (f) {
        return el('div', { class: 'refusal' }, [el('span', { class: 'code', text: f.code + '  ' + f.path, dir: 'ltr' }),
          el('span', { text: hint(f.code) }), el('span', { class: 'detail', text: f.message, dir: 'ltr', lang: 'en' })]);
      }));
    } else {
      st.className = 'status bad'; st.textContent = hint(r.error && r.error.code);
    }
    var steps = r.ok ? r.steps : [];
    $('incNote').textContent = r.ok && r.incremental ? t('compile.incremental') : '';
    var kinds = ['all'].concat(r.ok ? Object.keys(r.kinds) : []);
    if (kinds.indexOf(ui.kind) < 0) ui.kind = 'all';
    $('kinds').replaceChildren.apply($('kinds'), kinds.map(function (k) {
      var n = k === 'all' ? steps.length : r.kinds[k];
      var b = el('button', { type: 'button', class: 'chip', 'aria-pressed': String(k === ui.kind), dir: 'ltr', text: (k === 'all' ? t('compile.all') : k) + ' · ' + n });
      b.addEventListener('click', function () { ui.kind = k; renderCompile(); });
      return b;
    }));
    $('steps').replaceChildren.apply($('steps'), steps.filter(function (s) { return ui.kind === 'all' || s.kind === ui.kind; }).map(function (s) {
      return el('tr', {}, [el('td', { class: 'num', text: s.seq }), el('td', { class: 'num', text: s.phase }),
        el('td', { class: 'mono', text: s.kind, dir: 'ltr' }),
        el('td', { class: 'mono', dir: 'ltr', text: s.subject.kind + (s.subject.id ? ' ' + s.subject.id : '') + (s.property ? ' ' + s.property : '') }),
        el('td', { text: s.impact }), el('td', { text: s.ddlImpact }),
        el('td', { class: s.irreversibleReason ? 'err' : 'hint', text: s.irreversibleReason ? t('reason.' + s.irreversibleReason) : t('steps.reversible') })]);
    }));
  }

  /* ------------------------------------------------------------ apply, rollback, export */
  function busy(on) { ['applyBtn', 'rollbackBtn', 'failBtn'].forEach(function (i) { $(i).disabled = on; }); }
  function runApply(failAt) {
    busy(true); data.apply = { pending: true }; renderApply();
    api('POST', '/api/apply', failAt ? { failAtStep: failAt } : {}).then(function (r) { data.apply = r; afterSite(); });
  }
  function runRollback() {
    busy(true);
    api('POST', '/api/rollback').then(function (r) { r.isRollback = true; data.apply = r; afterSite(); });
  }
  function afterSite() { busy(false); renderApply(); loadExport(); api('GET', '/api/state').then(function (s) { if (s.ok) { data.state = s; renderState(); } }); }
  function kv(pairs) {
    return el('dl', { class: 'kv' }, [].concat.apply([], pairs.filter(Boolean).map(function (p) {
      return [el('dt', { text: p[0] }), el('dd', { class: p[2] || '', text: p[1], dir: p[2] ? 'ltr' : null })];
    })));
  }
  function renderApply() {
    var r = data.apply, list = $('stages'), out = $('applyResult');
    var stages = (r && r.stages) || [], byName = {};
    stages.forEach(function (s) { byName[s.stage] = s.status; });
    var names = STAGES.concat(byName.compensate ? ['compensate'] : []);
    list.replaceChildren.apply(list, names.map(function (n) {
      var stt = byName[n];
      return el('li', { class: stt === 'done' ? 'done' : stt === 'failed' ? 'failed' : '' },
        [el('span', { 'aria-hidden': 'true', text: stt === 'done' ? '✓' : stt === 'failed' ? '✕' : '○' }), t('stage.' + n), el('span', { class: 'sr', text: t('stageStatus.' + (stt || 'pending')) })]);
    }));
    var total = (r && r.stepCount) || 0, applied = r && r.stepStatus ? (r.stepStatus.applied || 0) : 0;
    $('bar').style.width = (total ? applied / total * 100 : 0) + '%';
    $('bar').parentNode.className = 'bar' + (r && r.ok === false ? ' bad' : '');
    $('stepCount').textContent = t('apply.steps', { a: applied, n: total });
    var pc = r && r.postConditions;
    $('pcCount').textContent = pc ? t('apply.pcs', { p: pc.passed, n: pc.total }) : '';
    if (!r) { out.replaceChildren(el('p', { class: 'hint', text: t('apply.idle') })); return; }
    if (r.pending) { out.replaceChildren(el('p', { class: 'hint', text: t('apply.running') })); return; }
    var head;
    if (r.refusals) {
      head = el('div', { class: 'status bad' }, [el('b', { text: t('apply.compileRefused', { n: r.refusals.length }) }), el('span', { class: 'hint', text: t('apply.nothingApplied') })]);
      out.replaceChildren(head, el('div', { class: 'refusals' }, r.refusals.map(function (f) {
        return el('div', { class: 'refusal' }, [el('span', { class: 'code', text: f.code + '  ' + f.path, dir: 'ltr' }), el('span', { text: hint(f.code) })]);
      })));
      return;
    }
    if (!r.status) {
      out.replaceChildren(el('div', { class: 'status bad' }, [el('b', { text: hint(r.error && r.error.code) }),
        el('span', { class: 'mono', dir: 'ltr', text: (r.error ? r.error.code + ' ' + r.error.path : '') + (r.error && r.error.reasonCode ? ' · ' + r.error.reasonCode : '') })]));
      return;
    }
    head = el('div', { class: 'status ' + (r.ok ? 'ok' : 'bad') }, [el('b', { text: t('status.' + r.status) }),
      r.error ? el('span', { text: hint(r.error.code) }) : null,
      r.error ? el('span', { class: 'mono', dir: 'ltr', text: r.error.code + ' ' + r.error.path + (r.error.reasonCode ? ' · ' + r.error.reasonCode : '') }) : null]);
    var rows = r.isRollback ? [
      r.ok ? [t('apply.history'), String(r.site.historyDepth)] : null,
      [t('apply.siteChanged'), r.siteChanged ? t('yes') : t('no')],
      [t('apply.hashBefore'), r.exportHashBefore, 'mono'], [t('apply.hashAfter'), r.exportHashAfter, 'mono']
    ] : [
      [t('apply.kind'), r.incremental ? t('apply.incremental') : t('apply.full')],
      [t('apply.compiledId'), r.compiledArtifactId, 'mono'], [t('apply.appliedId'), r.artifactId, 'mono'],
      r.droppedFields ? [t('apply.dropped'), t('apply.droppedText', { n: r.droppedFields })] : null,
      [t('apply.verdict'), r.verdict], [t('apply.approvals'), r.approvalsGranted.join(', ')],
      [t('apply.predicted'), r.predictedExportHash, 'mono'], [t('apply.hashAfter'), r.exportHashAfter, 'mono'],
      [t('apply.hashMatch'), r.status === 'compensated' ? (r.exportHashAfter === r.exportHashBefore ? t('apply.restored') : t('no')) : (r.exportHashMatches ? t('yes') : t('no'))]
    ];
    var why = r.isRollback && !r.ok && r.error && has('reason.' + r.error.reasonCode) ? el('p', { class: 'err', text: t('reason.' + r.error.reasonCode) }) : null;
    var done = r.isRollback && r.ok ? el('p', { class: 'hint', text: t('apply.rolledBack') }) : null;
    out.replaceChildren(head, why, done, kv(rows));
  }
  function loadExport() { api('GET', '/api/export').then(function (r) { data.exp = r; renderExport(); }); }
  function renderExport() {
    var r = data.exp, box = $('siteNow');
    if (!r) return;
    if (r.ok === false) { box.replaceChildren(el('p', { class: 'err', text: hint(r.error.code) })); return; }
    if (!r.provisioned) { box.replaceChildren(el('p', { class: 'hint', text: t('site.none') })); return; }
    var c = r.counts;
    var stats = ['entities', 'fields', 'components', 'roles', 'workflows', 'approvals', 'reports', 'locations'].map(function (k) {
      return el('div', { class: 'stat' }, [el('b', { text: c[k] }), el('span', { text: t('count.' + k) })]);
    });
    var company = r.company && r.company.legalName ? loc(r.company.legalName) : t('site.noCompany');
    box.replaceChildren(el('div', { class: 'stats' }, stats),
      kv([[t('site.company'), company], [t('site.revision'), r.revision === null ? '-' : String(r.revision)],
        [t('site.retained'), String(r.retainedCount)], [t('site.hash'), r.exportHash, 'mono']]),
      el('div', { class: 'chips' }, r.names.entities.map(function (e) { return el('span', { class: 'tag', text: loc(e.labels) || e.id }); })));
  }

  /* ------------------------------------------------------------ brand */
  function loadTheme() { api('POST', '/api/theme').then(function (r) { data.theme = r; renderTheme(); }); }
  function swatch(v) { var s = el('span', { class: 'swatch' }); if (SAFE_TOKEN.test(v)) s.style.setProperty('background-color', v); return s; }
  function preview(box, tokens, mode) {
    Object.keys(tokens).forEach(function (k) { if (/^--[a-z0-9-]+$/.test(k) && SAFE_TOKEN.test(tokens[k])) box.style.setProperty(k, tokens[k]); });
    box.replaceChildren(el('span', { class: 'hint', text: t('brand.mode.' + mode) }), el('div', { class: 'pacc' }),
      el('div', { class: 'pcard' }, [el('span', { class: 'ptitle', text: t('brand.pvTitle') }), el('span', { class: 'pmuted', text: t('brand.pvBody') }),
        el('span', { class: 'psel', text: t('brand.pvSelected') }),
        el('div', { class: 'row wrap' }, [el('button', { type: 'button', class: 'pbtn', text: t('brand.pvPrimary') }), el('button', { type: 'button', class: 'psec', text: t('brand.pvSecondary') })])]),
      el('span', { class: 'plink', text: t('brand.pvLink') }));
  }
  function renderTheme() {
    var r = data.theme, st = $('brandStatus');
    if (!r) { st.textContent = t('brand.loading'); return; }
    if (!r.resolved) { st.className = 'status bad'; st.textContent = hint(r.error && r.error.code); return; }
    var refused = r.codes.refusal.length > 0;
    st.className = 'status ' + (refused ? 'bad' : 'ok');
    fill(st, el('b', { text: refused ? t('brand.refused') : t('brand.accepted') }), swatch(r.input || ''),
      el('span', { class: 'mono', dir: 'ltr', text: (r.input || '') + ' → ' + r.resolved.light['--color-primary'] + ' / ' + r.resolved.dark['--color-primary'] }),
      refused ? el('span', { text: t('brand.platformKept') }) : null);
    preview($('pvLight'), r.resolved.light, 'light');
    preview($('pvDark'), r.resolved.dark, 'dark');
    $('findings').replaceChildren.apply($('findings'), r.findings.length ? r.findings.map(function (f) {
      var p = f.params || {};
      return el('div', { class: 'find' }, [el('span', { class: 'badge ' + (f.severity === 'refusal' ? 'bad' : f.severity === 'warning' ? 'warn' : 'ok'), text: t('sev.' + f.severity) }),
        el('span', { text: hint(f.code) }), p.from ? swatch(p.from) : null, p.to ? swatch(p.to) : null,
        el('span', { class: 'mono', dir: 'ltr', text: f.code + (p.from ? ' ' + p.from + ' → ' + p.to : '') + (p.mode ? ' (' + p.mode + ')' : '') })]);
    }) : [el('p', { class: 'hint', text: t('brand.noFindings') })]);
  }

  /* ------------------------------------------------------------ invoice */
  function seg(box, values, current, label, onPick) {
    box.setAttribute('aria-label', label);
    box.replaceChildren.apply(box, values.map(function (v) {
      var b = el('button', { type: 'button', 'aria-pressed': String(v[0] === current), text: v[1] });
      b.addEventListener('click', function () { onPick(v[0]); });
      return b;
    }));
  }
  function loadInvoice() {
    var q = '/api/invoice?market=' + encodeURIComponent(ui.market) + '&lang=' + encodeURIComponent(ui.invLang) + (ui.invoice ? '&invoice=' + encodeURIComponent(ui.invoice) : '');
    api('GET', q).then(function (r) { data.invoice = r; renderInvoice(); });
  }
  function renderInvoice() {
    seg($('marketSeg'), MARKETS.map(function (m) { return [m, t('market.' + m)]; }), ui.market, t('inv.market'), function (m) { ui.market = m; ui.invoice = null; loadInvoice(); });
    seg($('invLangSeg'), [['en', I18N.en['lang.self']], ['ar', I18N.ar['lang.self']]], ui.invLang, t('inv.language'), function (l) { ui.invLang = l; loadInvoice(); });
    var r = data.invoice, box = $('invoice');
    if (!r) return;
    if (!r.ok) { box.replaceChildren(el('p', { class: 'err', text: hint(r.error && r.error.code) })); return; }
    var L = r.lang, T = function (k, v) { return tIn(L, k, v); }, x = r.expected, cur = r.currency;
    $('invSel').replaceChildren.apply($('invSel'), r.invoices.map(function (id) { return el('option', { value: id, text: id, selected: id === r.invoice.id }); }));
    $('invNotice').textContent = t('inv.notice', { rate: r.vatRatePercent });
    box.dir = r.dir; box.lang = L;
    var party = function (title, name, vat) { return el('div', {}, [el('b', { text: title }), el('span', { text: name }), vat ? el('span', { class: 'hint', text: T('inv.vatNo') + ' ' + vat }) : null]); };
    var table = el('table', {}, [el('thead', {}, [el('tr', {}, [el('th', { text: T('inv.item') }), el('th', { class: 'num', text: T('inv.qty') }),
      el('th', { class: 'num', text: T('inv.price') }), el('th', { class: 'num', text: T('inv.lineDisc') }), el('th', { class: 'num', text: T('inv.net') })])]),
      el('tbody', {}, r.lines.map(function (l) {
        return el('tr', {}, [el('td', { class: 'wrap', text: l.name[L] || l.item }), el('td', { class: 'num', text: l.quantity + ' ' + (l.unit[L] || '') }),
          el('td', { class: 'num', text: l.unitPrice }), el('td', { class: 'num', text: l.discountPercent + '%' }), el('td', { class: 'num', text: l.lineNet })]);
      }))]);
    var row = function (k, v, c) { return el('div', { class: c || '' }, [el('span', { text: k }), el('span', { text: v, dir: 'ltr' })]); };
    box.replaceChildren(
      el('div', { class: 'inv-head' }, [el('div', {}, [el('h3', { text: T('inv.title') }), el('span', { class: 'hint', text: T('inv.no') + ' ' + r.invoice.id }),
        el('span', { class: 'hint', text: T('inv.date') + ' ' + r.invoice.date }), el('span', { class: 'hint', text: T('inv.order') + ' ' + (r.invoice.salesOrder || '-') })]),
        party(T('inv.seller'), r.seller.legalName[L], r.seller.vatNumber), party(T('inv.buyer'), r.buyer.name[L] || r.buyer.code, r.buyer.vatNumber)]),
      el('div', { class: 'scroll short' }, [table]),
      el('div', { class: 'totals' }, [row(T('inv.subtotal'), x.subtotal), row(T('inv.docDisc', { p: r.invoice.discountPercent }), x.document_discount),
        row(T('inv.netTotal'), x.net_total), row(T('inv.vat', { p: r.vatRatePercent }), x.vat_amount), row(T('inv.total', { c: cur }), x.total, 'grand')]),
      el('p', { class: 'hint', text: T('inv.synthetic') }));
    var tagNames = ['', 'inv.tag1', 'inv.tag2', 'inv.tag3', 'inv.tag4', 'inv.tag5'];
    $('tlv').replaceChildren.apply($('tlv'), Object.keys(r.qr.tags).map(function (k) {
      return el('tr', {}, [el('td', { class: 'mono', text: k }), el('td', { text: t(tagNames[+k] || 'inv.tagOther') }), el('td', { class: 'wrap', dir: 'auto', text: r.qr.tags[k] })]);
    }));
    $('b64').value = r.qr.payload;
    try { $('qr').replaceChildren(window.StudioQR.toSvg(document, window.StudioQR.encode(r.qr.payload), 4)); }
    catch (e) { $('qr').replaceChildren(el('p', { class: 'err', text: t('inv.qrFailed') })); }
  }

  /* ------------------------------------------------------------ wiring */
  function load() {
    api('GET', '/api/state').then(function (s) {
      if (!s.ok) { showErr('globalErr', s); return; }
      data.state = s; renderState(); runCompile(); loadTheme(); loadExport(); loadInvoice();
    });
  }
  function wire() {
    $('langBtn').addEventListener('click', function () { ui.lang = ui.lang === 'en' ? 'ar' : 'en'; keep('studio.lang', ui.lang); rerender(); });
    $('themeBtn').addEventListener('click', function () {
      ui.theme = { system: 'light', light: 'dark', dark: 'system' }[ui.theme] || 'system'; keep('studio.theme', ui.theme); applyChrome();
    });
    $('resetBtn').addEventListener('click', function () {
      api('POST', '/api/reset').then(function (s) { if (s.ok) { data.apply = null; ui.entity = null; data.state = s; renderState(); renderApply(); runCompile(); loadTheme(); loadExport(); } else showErr('globalErr', s); });
    });
    document.querySelectorAll('#tabs [role=tab]').forEach(function (b, i, all) {
      b.addEventListener('click', function () { ui.tab = b.getAttribute('data-tab'); keep('studio.tab', ui.tab); applyChrome(); });
      b.addEventListener('keydown', function (ev) {
        var d = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
        if (!d) return;
        if (document.documentElement.dir === 'rtl') d = -d;
        var next = all[(i + d + all.length) % all.length];
        next.click(); next.focus();
      });
    });
    ['legalEn', 'legalAr', 'tradeEn', 'tradeAr'].forEach(function (i) { $(i).addEventListener('input', function () { debounce('company', 400, saveCompany); }); });
    ['entEn', 'entAr'].forEach(function (i) { $(i).addEventListener('input', function () { debounce('labels', 400, saveLabels); }); });
    $('entitySel').addEventListener('change', function () { ui.entity = $('entitySel').value; $('labelErr').hidden = true; renderState(); });
    $('colorPick').addEventListener('input', function () { $('colorHex').value = $('colorPick').value.toUpperCase(); debounce('brand', 250, function () { saveColour($('colorHex').value); }); });
    $('colorHex').addEventListener('input', function () { debounce('brand', 500, function () { saveColour($('colorHex').value.trim()); }); });
    $('applyBtn').addEventListener('click', function () { runApply(null); });
    $('failBtn').addEventListener('click', function () { runApply(parseInt($('failStep').value, 10) || 1); });
    $('rollbackBtn').addEventListener('click', runRollback);
    $('invSel').addEventListener('change', function () { ui.invoice = $('invSel').value; loadInvoice(); });
    $('copyBtn').addEventListener('click', function () {
      if (navigator.clipboard) navigator.clipboard.writeText($('b64').value).catch(function () { $('b64').select(); });
      else $('b64').select();
    });
  }
  wire(); rerender(); load();
})();
