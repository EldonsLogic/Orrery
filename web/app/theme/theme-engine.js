// Theme engine (BRD-005). Layer 4 of the token layering: user preference selects
// light | dark | system. It never writes a colour or tenant token.
// Framework-agnostic ES module. No DOM or network access at import time:
// root, storage, matchMedia and the remote persister are injected.

export const MODES = Object.freeze(['light', 'dark', 'system']);
export const DEFAULT_MODE = 'system';
export const KEY_PREFIX = 'platform.theme.v1';

export const CODES = Object.freeze({
  BAD_MODE: 'THM-MODE-INVALID',
  NO_IDS: 'THM-IDS-MISSING',
  REMOTE_LOAD_FAILED: 'THM-REMOTE-LOAD-FAILED',
  REMOTE_SAVE_FAILED: 'THM-REMOTE-SAVE-FAILED',
});

export class ThemeError extends Error {
  constructor(code, message) {
    super(message || code);
    this.name = 'ThemeError';
    this.code = code;
  }
}

export function isMode(v) {
  return typeof v === 'string' && MODES.includes(v);
}

// Strict: only the exact three strings; anything else (tampered, wrong type) -> 'system'.
export function sanitiseMode(v) {
  return isMode(v) ? v : DEFAULT_MODE;
}

export function resolveEffective(mode, systemPrefersDark) {
  if (!isMode(mode)) throw new ThemeError(CODES.BAD_MODE, 'invalid theme mode');
  if (mode === 'system') return systemPrefersDark ? 'dark' : 'light';
  return mode;
}

function validId(v) {
  return typeof v === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(v);
}

// Key is namespaced by tenant and user so one user never reads another's value.
export function storageKey(tenantId, userId) {
  if (!validId(tenantId) || !validId(userId)) {
    throw new ThemeError(CODES.NO_IDS, 'tenantId and userId are required');
  }
  return `${KEY_PREFIX}.${tenantId}.${userId}`;
}

function applyToRoot(root, mode, effective) {
  if (!root) return;
  if (mode === 'system') {
    // CSS prefers-color-scheme rules apply when data-theme is absent.
    root.removeAttribute('data-theme');
    if (root.style) root.style.colorScheme = 'light dark';
  } else {
    root.setAttribute('data-theme', mode);
    if (root.style) root.style.colorScheme = effective;
  }
}

export function createThemeEngine({ root, storage, matchMedia, userId, tenantId, remote } = {}) {
  const key = storageKey(tenantId, userId); // throws THM-IDS-MISSING

  let mode = DEFAULT_MODE;
  let memory = null; // in-memory fallback when storage fails
  let storageOk = true;
  let mql = null;
  const subs = new Set();
  let lastCode = null;
  let writeSeq = 0;

  try { mql = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null; } catch { mql = null; }
  const systemDark = () => Boolean(mql && mql.matches);

  function readStored() {
    try {
      if (!storage) throw new Error('no storage');
      return storage.getItem(key);
    } catch {
      storageOk = false;
      return memory;
    }
  }
  function writeStored(v) {
    memory = v;
    try {
      if (!storage) throw new Error('no storage');
      storage.setItem(key, v);
    } catch {
      storageOk = false;
    }
  }

  function snapshot() {
    return { mode, effective: resolveEffective(mode, systemDark()) };
  }
  function apply() {
    const s = snapshot();
    applyToRoot(root, s.mode, s.effective);
    return s;
  }
  function notify() {
    const s = snapshot();
    for (const fn of [...subs]) {
      try { fn(s); } catch { /* a bad subscriber must not break the engine */ }
    }
  }

  mode = sanitiseMode(readStored());
  apply();

  // Only react to system changes while in 'system' mode.
  const onSystem = () => {
    if (mode !== 'system') return;
    apply();
    notify();
  };
  if (mql) {
    if (typeof mql.addEventListener === 'function') mql.addEventListener('change', onSystem);
    else if (typeof mql.addListener === 'function') mql.addListener(onSystem);
  }

  function setLocal(next, persistRemote) {
    if (!isMode(next)) throw new ThemeError(CODES.BAD_MODE, 'invalid theme mode');
    const changed = next !== mode;
    mode = next;
    writeStored(next);
    apply();
    if (changed) notify();
    if (persistRemote && remote && typeof remote.save === 'function') {
      const seq = ++writeSeq;
      Promise.resolve()
        .then(() => remote.save({ tenantId, userId, mode: next }))
        .catch(() => { if (seq === writeSeq) lastCode = CODES.REMOTE_SAVE_FAILED; });
    }
    return snapshot();
  }

  return {
    get: () => snapshot(),
    set: (next) => setLocal(next, true),
    subscribe(fn) {
      if (typeof fn !== 'function') throw new TypeError('subscriber must be a function');
      subs.add(fn);
      return () => { subs.delete(fn); };
    },
    // Async, optional. Last write wins: a local set() made while loading beats the remote value.
    // Never throws; resolves { ok, code?, mode }.
    async syncRemote() {
      if (!remote || typeof remote.load !== 'function') return { ok: false, code: CODES.REMOTE_LOAD_FAILED, mode };
      const seqAtStart = writeSeq;
      try {
        const v = await remote.load({ tenantId, userId });
        if (writeSeq !== seqAtStart) return { ok: true, mode, stale: true };
        if (!isMode(v)) return { ok: true, mode, ignored: true }; // invalid or absent remote value
        setLocal(v, false);
        return { ok: true, mode };
      } catch {
        lastCode = CODES.REMOTE_LOAD_FAILED;
        return { ok: false, code: CODES.REMOTE_LOAD_FAILED, mode };
      }
    },
    status: () => ({ persistent: storageOk, lastCode }),
    destroy() {
      subs.clear();
      if (mql) {
        if (typeof mql.removeEventListener === 'function') mql.removeEventListener('change', onSystem);
        else if (typeof mql.removeListener === 'function') mql.removeListener(onSystem);
      }
    },
  };
}

// Text for an inline <script> that sets data-theme before first paint.
// `key` must come from storageKey(tenantId, userId) (server-side, ids validated).
// CSP: an inline script needs a nonce or a hash of exactly this text; compute it at serve time.
export function bootScript(key) {
  if (typeof key !== 'string' || !/^[A-Za-z0-9_.-]{1,200}$/.test(key)) {
    throw new ThemeError(CODES.NO_IDS, 'invalid storage key');
  }
  return `(function(){try{var m=localStorage.getItem(${JSON.stringify(key)});` +
    `if(m==="light"||m==="dark"){document.documentElement.setAttribute("data-theme",m);` +
    `document.documentElement.style.colorScheme=m}}catch(e){}})();`;
}
