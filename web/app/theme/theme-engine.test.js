import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MODES, resolveEffective, sanitiseMode, storageKey, createThemeEngine, bootScript, CODES,
} from './theme-engine.js';

function fakeRoot() {
  const attrs = new Map();
  const style = new Proxy({ writes: [] }, {
    set(t, k, v) { t.writes.push(k); t[k] = v; return true; },
  });
  return {
    style,
    setAttribute: (k, v) => attrs.set(k, v),
    removeAttribute: (k) => attrs.delete(k),
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    attrs,
  };
}
function fakeStorage(init = {}) {
  const m = new Map(Object.entries(init));
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), m };
}
function fakeMM(dark = false) {
  const ls = new Set();
  const mql = {
    matches: dark,
    addEventListener: (_, f) => ls.add(f),
    removeEventListener: (_, f) => ls.delete(f),
  };
  return { mm: () => mql, flip(v) { mql.matches = v; [...ls].forEach((f) => f({ matches: v })); }, ls };
}
const ids = { tenantId: 't1', userId: 'u1' };

test('mode validation', () => {
  assert.deepEqual([...MODES], ['light', 'dark', 'system']);
  for (const bad of ['', 'LIGHT', 'auto', null, undefined, 1, {}, ['dark']]) assert.equal(sanitiseMode(bad), 'system');
  assert.throws(() => resolveEffective('auto', true), { code: CODES.BAD_MODE });
  const e = createThemeEngine({ root: fakeRoot(), storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids });
  assert.throws(() => e.set('purple'), { code: CODES.BAD_MODE });
});

test('effective resolution', () => {
  assert.equal(resolveEffective('light', true), 'light');
  assert.equal(resolveEffective('dark', false), 'dark');
  assert.equal(resolveEffective('system', true), 'dark');
  assert.equal(resolveEffective('system', false), 'light');
});

test('applies data-theme; system removes attribute', () => {
  const root = fakeRoot();
  const e = createThemeEngine({ root, storage: fakeStorage(), matchMedia: fakeMM(true).mm, ...ids });
  assert.equal(root.getAttribute('data-theme'), null);
  assert.deepEqual(e.get(), { mode: 'system', effective: 'dark' });
  e.set('light');
  assert.equal(root.getAttribute('data-theme'), 'light');
  assert.equal(root.style.colorScheme, 'light');
  e.set('system');
  assert.equal(root.getAttribute('data-theme'), null);
});

test('system change listener only acts in system mode', () => {
  const root = fakeRoot(); const mm = fakeMM(false);
  const e = createThemeEngine({ root, storage: fakeStorage(), matchMedia: mm.mm, ...ids });
  const seen = [];
  e.subscribe((s) => seen.push(s.effective));
  mm.flip(true);
  assert.deepEqual(seen, ['dark']);
  e.set('light'); seen.length = 0;
  mm.flip(false); mm.flip(true);
  assert.deepEqual(seen, []);
  assert.equal(root.getAttribute('data-theme'), 'light');
  e.destroy();
  assert.equal(mm.ls.size, 0);
});

test('per-user and per-tenant key isolation', () => {
  const st = fakeStorage();
  const mk = (tenantId, userId) => createThemeEngine({ root: fakeRoot(), storage: st, matchMedia: fakeMM().mm, tenantId, userId });
  mk('t1', 'u1').set('dark');
  assert.equal(mk('t1', 'u2').get().mode, 'system');
  assert.equal(mk('t2', 'u1').get().mode, 'system');
  assert.equal(mk('t1', 'u1').get().mode, 'dark');
  assert.notEqual(storageKey('t1', 'u1'), storageKey('t1', 'u2'));
  assert.notEqual(storageKey('t1', 'u1'), storageKey('t2', 'u1'));
  assert.equal(st.m.size, 1);
});

test('missing or malformed ids are refused', () => {
  for (const bad of [{}, { tenantId: 't' }, { userId: 'u' }, { tenantId: '', userId: 'u' }, { tenantId: 'a.b', userId: 'u' }, { tenantId: 't', userId: 'u\n1' }]) {
    assert.throws(() => createThemeEngine({ root: fakeRoot(), storage: fakeStorage(), matchMedia: fakeMM().mm, ...bad }), { code: CODES.NO_IDS });
  }
});

test('corrupted storage falls back to system without throwing', () => {
  const key = storageKey('t1', 'u1');
  for (const v of ['"dark"', 'DARK', '<script>', '', 'dark ', '{"mode":"dark"}']) {
    const e = createThemeEngine({ root: fakeRoot(), storage: fakeStorage({ [key]: v }), matchMedia: fakeMM().mm, ...ids });
    assert.equal(e.get().mode, 'system');
  }
});

test('throwing storage degrades to memory', () => {
  const bad = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('quota'); } };
  const root = fakeRoot();
  const e = createThemeEngine({ root, storage: bad, matchMedia: fakeMM().mm, ...ids });
  assert.doesNotThrow(() => e.set('dark'));
  assert.equal(e.get().mode, 'dark');
  assert.equal(root.getAttribute('data-theme'), 'dark');
  assert.equal(e.status().persistent, false);
  const none = createThemeEngine({ root: fakeRoot(), storage: undefined, matchMedia: undefined, ...ids });
  assert.equal(none.get().effective, 'light');
  none.set('dark');
  assert.equal(none.get().mode, 'dark');
});

test('subscribe and unsubscribe', () => {
  const e = createThemeEngine({ root: fakeRoot(), storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids });
  const calls = [];
  const un = e.subscribe((s) => calls.push(s.mode));
  e.set('dark'); un(); e.set('light');
  assert.deepEqual(calls, ['dark']);
  e.subscribe(() => { throw new Error('boom'); });
  assert.doesNotThrow(() => e.set('system'));
});

test('remote persister: load, last write wins, coded fallback', async () => {
  const saved = [];
  const root = fakeRoot();
  const e = createThemeEngine({ root, storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids,
    remote: { load: async () => 'dark', save: async (x) => { saved.push(x); } } });
  assert.deepEqual(await e.syncRemote(), { ok: true, mode: 'dark' });
  assert.equal(root.getAttribute('data-theme'), 'dark');
  assert.equal(saved.length, 0); // remote-originated values are not echoed back
  e.set('light'); await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(saved, [{ tenantId: 't1', userId: 'u1', mode: 'light' }]);

  // local set during a slow load wins
  let release; const gate = new Promise((r) => { release = r; });
  const e2 = createThemeEngine({ root: fakeRoot(), storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids,
    remote: { load: async () => { await gate; return 'dark'; }, save: async () => {} } });
  const p = e2.syncRemote(); e2.set('light'); release();
  assert.equal((await p).stale, true);
  assert.equal(e2.get().mode, 'light');

  // failures and junk
  const e3 = createThemeEngine({ root: fakeRoot(), storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids,
    remote: { load: async () => { throw new Error('x'); }, save: async () => { throw new Error('y'); } } });
  assert.deepEqual(await e3.syncRemote(), { ok: false, code: CODES.REMOTE_LOAD_FAILED, mode: 'system' });
  e3.set('dark'); await new Promise((r) => setTimeout(r, 0));
  assert.equal(e3.status().lastCode, CODES.REMOTE_SAVE_FAILED);
  assert.equal(e3.get().mode, 'dark');
  const e4 = createThemeEngine({ root: fakeRoot(), storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids, remote: { load: async () => 'neon' } });
  assert.equal((await e4.syncRemote()).ignored, true);
  assert.equal(e4.get().mode, 'system');
});

test('never writes colour or tenant tokens on root.style', () => {
  const root = fakeRoot();
  const e = createThemeEngine({ root, storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids });
  for (const m of ['dark', 'light', 'system']) e.set(m);
  assert.ok(root.style.writes.every((k) => k === 'colorScheme'), root.style.writes.join());
  assert.deepEqual([...root.attrs.keys()].filter((k) => k !== 'data-theme'), []);
});

test('idempotence', () => {
  const root = fakeRoot();
  const e = createThemeEngine({ root, storage: fakeStorage(), matchMedia: fakeMM().mm, ...ids });
  let n = 0; e.subscribe(() => n++);
  e.set('dark'); e.set('dark'); e.set('dark');
  assert.equal(n, 1);
  assert.equal(root.getAttribute('data-theme'), 'dark');
});

test('bootScript', () => {
  const key = storageKey('t1', 'u1');
  const s = bootScript(key);
  assert.ok(s.includes(JSON.stringify(key)));
  assert.ok(!s.includes('fetch') && !s.includes('XMLHttpRequest'));
  // execute against fakes
  const root = fakeRoot();
  new Function('localStorage', 'document', s)(fakeStorage({ [key]: 'dark' }), { documentElement: root });
  assert.equal(root.getAttribute('data-theme'), 'dark');
  const r2 = fakeRoot();
  new Function('localStorage', 'document', s)(fakeStorage({ [key]: 'evil' }), { documentElement: r2 });
  assert.equal(r2.getAttribute('data-theme'), null);
  assert.doesNotThrow(() => new Function('localStorage', 'document', s)({ getItem() { throw new Error(); } }, { documentElement: fakeRoot() }));
  assert.throws(() => bootScript('a"b'), { code: CODES.NO_IDS });
});
